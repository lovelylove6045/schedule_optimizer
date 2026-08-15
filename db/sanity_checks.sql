-- Sanity checks for the full-catalog load (db/load_catalog.py).
-- Run with any Postgres client, or `uv run python ../db/run_sanity_checks.py`
-- from backend/. See db/SUMMARY.md for what "correct" looks like for each one.

-- Query 1: Row counts per table, compared against the source JSON file's
-- array length (see the "Loaded ..." line load_catalog.py prints on a
-- successful run -- every number below should match it exactly).
SELECT 'colleges' AS table_name, COUNT(*) FROM colleges
UNION ALL SELECT 'departments', COUNT(*) FROM departments
UNION ALL SELECT 'subjects', COUNT(*) FROM subjects
UNION ALL SELECT 'courses', COUNT(*) FROM courses
UNION ALL SELECT 'course_groups', COUNT(*) FROM course_groups
UNION ALL SELECT 'course_group_courses', COUNT(*) FROM course_group_courses
UNION ALL SELECT 'course_relations', COUNT(*) FROM course_relations
UNION ALL SELECT 'academic_programs', COUNT(*) FROM academic_programs
UNION ALL SELECT 'academic_program_relationships', COUNT(*) FROM academic_program_relationships
UNION ALL SELECT 'requirement_sets', COUNT(*) FROM requirement_sets
UNION ALL SELECT 'program_requirement_sets', COUNT(*) FROM program_requirement_sets
UNION ALL SELECT 'requirement_nodes', COUNT(*) FROM requirement_nodes
UNION ALL SELECT 'course_rule_nodes', COUNT(*) FROM course_rule_nodes
ORDER BY table_name;

-- Query 2: No course should ever directly require itself. This should
-- always return 0 rows -- load_catalog.py loads course_rule_nodes.json
-- verbatim with no de-duplication logic, so this is really a check on the
-- source data, not the loader.
SELECT target_course_id, required_course_id, source_text
FROM course_rule_nodes
WHERE target_course_id = required_course_id;

-- Query 3: Strict-PREREQUISITE-only cycles (a course that indirectly
-- requires itself through a chain of *hard* prerequisites, ignoring
-- COREQUISITE/PRE_OR_COREQUISITE/RECOMMENDED edges, which are allowed to be
-- mutual). As of the full-catalog load this returns ~280 courses -- see
-- db/SUMMARY.md ("known limitation: language/ladder course clusters") for
-- why this is a real, expected property of the source data rather than a
-- bug: e.g. "Russian 1180 or above" is parsed as one COURSE node per
-- matching course, so every course at or above that level lists every
-- *other* course at that level as an acceptable (ANY) alternative,
-- including ones numbered higher than itself.
WITH RECURSIVE closure AS (
    SELECT target_course_id AS root, required_course_id AS reached, 1 AS depth
    FROM course_rule_nodes
    WHERE required_course_id IS NOT NULL AND requisite_type = 'PREREQUISITE'
    UNION
    SELECT c.root, crn.required_course_id, c.depth + 1
    FROM closure c
    JOIN course_rule_nodes crn ON crn.target_course_id = c.reached
    WHERE crn.required_course_id IS NOT NULL
      AND crn.requisite_type = 'PREREQUISITE'
      AND c.depth < 25
)
SELECT COUNT(DISTINCT root) AS self_reachable_course_count
FROM closure
WHERE root = reached;

-- Query 4: Spot-check one well-known program end-to-end -- Aerospace
-- Engineering BS should still show the same requirement tree it always
-- has (this program's data didn't change between the narrow-scope load and
-- the full-catalog load, only its surrounding context did).
SELECT rn.requirement_node_id, rn.parent_requirement_node_id, rn.node_type,
       rn.node_operator, rn.node_name, rn.required_course_id, rn.course_group_id
FROM requirement_nodes rn
JOIN requirement_sets rs ON rs.requirement_set_id = rn.requirement_set_id
JOIN program_requirement_sets prs ON prs.requirement_set_id = rs.requirement_set_id
JOIN academic_programs ap ON ap.academic_program_id = prs.academic_program_id
WHERE ap.program_code = 'AERO_BS_2026'
ORDER BY rn.requirement_node_id;

-- Query 5: Every academic program should now have at least one requirement
-- set attached (146 of 147 did in the source data at last check -- one
-- program, if any, having zero requirement sets is expected and not a
-- loader bug; a *large* number with zero would indicate one).
SELECT ap.academic_program_id, ap.program_code, ap.program_name
FROM academic_programs ap
LEFT JOIN program_requirement_sets prs ON prs.academic_program_id = ap.academic_program_id
WHERE prs.program_requirement_set_id IS NULL
ORDER BY ap.academic_program_id;
