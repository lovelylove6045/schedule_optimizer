-- Phase 1.3 sanity checks (see docs/PHASES.md) for the narrow Aerospace
-- Engineering BS + Minor load produced by load_catalog.py.
--
-- Run with (from repo root):
--   psql -h localhost -U postgres -d schedule_optimizer -f db/sanity_checks.sql

-- =============================================================================
-- 1. Full requirement tree for the primary program (Aerospace Engineering BS)
-- =============================================================================
-- requirement_nodes is a self-referencing tree per requirement_set; walk every
-- requirement_set attached to the program and print it depth-first.
WITH RECURSIVE req_tree AS (
    SELECT
        rn.requirement_node_id,
        rn.requirement_set_id,
        rn.parent_requirement_node_id,
        rn.node_type,
        rn.node_operator,
        rn.node_name,
        rn.required_course_id,
        rn.course_group_id,
        rn.required_credit_hours,
        rn.display_order,
        0 AS depth,
        LPAD(rn.display_order::text, 4, '0') AS sort_path
    FROM requirement_nodes rn
    JOIN program_requirement_sets prs ON prs.requirement_set_id = rn.requirement_set_id
    JOIN academic_programs ap ON ap.academic_program_id = prs.academic_program_id
    WHERE ap.program_code = 'AERO_BS_2026'
      AND rn.parent_requirement_node_id IS NULL

    UNION ALL

    SELECT
        rn.requirement_node_id,
        rn.requirement_set_id,
        rn.parent_requirement_node_id,
        rn.node_type,
        rn.node_operator,
        rn.node_name,
        rn.required_course_id,
        rn.course_group_id,
        rn.required_credit_hours,
        rn.display_order,
        t.depth + 1,
        t.sort_path || '.' || LPAD(rn.display_order::text, 4, '0')
    FROM requirement_nodes rn
    JOIN req_tree t ON rn.parent_requirement_node_id = t.requirement_node_id
)
SELECT
    rs.requirement_set_code,
    REPEAT('  ', t.depth) || t.node_name AS node,
    t.node_type,
    t.node_operator,
    (SELECT s.subject_code || ' ' || c.course_number
       FROM courses c JOIN subjects s ON s.subject_id = c.subject_id
      WHERE c.course_id = t.required_course_id) AS required_course,
    (SELECT cg.course_group_name FROM course_groups cg WHERE cg.course_group_id = t.course_group_id) AS course_group,
    t.required_credit_hours
FROM req_tree t
JOIN requirement_sets rs ON rs.requirement_set_id = t.requirement_set_id
ORDER BY rs.requirement_set_id, t.sort_path;


-- =============================================================================
-- 2. Full prerequisite closure for an upper-level course (AERO ENG 4780,
--    Aerospace Systems Design I -- the senior design capstone)
-- =============================================================================
-- course_rule_nodes.target_course_id -> required_course_id is itself a graph;
-- recurse from the target course down through each prerequisite's own
-- prerequisites. Uses UNION (not UNION ALL) plus a final GROUP BY MIN(depth)
-- to report each course once at its shortest distance -- a naive "all paths"
-- version re-visits shared foundational courses (Math/Physics) once per
-- diamond-shaped path and floods the output with duplicates.
WITH RECURSIVE prereq_closure(course_id, depth) AS (
    SELECT tc.course_id, 0
    FROM courses tc
    JOIN subjects s ON s.subject_id = tc.subject_id
    WHERE s.subject_code = 'AERO ENG' AND tc.course_number = '4780'

    UNION

    SELECT crn.required_course_id, pc.depth + 1
    FROM course_rule_nodes crn
    JOIN prereq_closure pc ON crn.target_course_id = pc.course_id
    WHERE crn.required_course_id IS NOT NULL
)
SELECT
    MIN(pc.depth) AS min_depth,
    s.subject_code || ' ' || c.course_number AS course,
    c.course_title
FROM prereq_closure pc
JOIN courses c ON c.course_id = pc.course_id
JOIN subjects s ON s.subject_id = c.subject_id
WHERE pc.depth > 0
GROUP BY s.subject_code, c.course_number, c.course_title
ORDER BY min_depth, course;


-- =============================================================================
-- 3. All courses satisfying a specific course_group (MAE Technical Electives,
--    the pool backing the Aerospace BS's 9-credit technical elective requirement)
-- =============================================================================
-- course_group membership is a flat many-to-many, not a tree, so a plain join
-- is the right tool here (no recursion needed).
SELECT
    cg.course_group_code,
    cg.course_group_name,
    s.subject_code,
    c.course_number,
    c.course_title,
    c.credit_hours,
    c.course_level
FROM course_group_courses cgc
JOIN course_groups cg ON cg.course_group_id = cgc.course_group_id
JOIN courses c ON c.course_id = cgc.course_id
JOIN subjects s ON s.subject_id = c.subject_id
WHERE cg.course_group_code = 'AERO_MAE_TECH_2026'
ORDER BY s.subject_code, c.course_number;
