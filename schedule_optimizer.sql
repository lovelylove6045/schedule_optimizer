-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.departments (
  department_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  department_code character varying NOT NULL UNIQUE,
  department_name character varying NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  college_id integer,
  CONSTRAINT departments_pkey PRIMARY KEY (department_id),
  CONSTRAINT departments_college_fk FOREIGN KEY (college_id) REFERENCES public.colleges(college_id)
);
CREATE TABLE public.subjects (
  subject_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  department_id integer NOT NULL,
  subject_code character varying NOT NULL UNIQUE,
  subject_name character varying NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT subjects_pkey PRIMARY KEY (subject_id),
  CONSTRAINT subjects_department_fk FOREIGN KEY (department_id) REFERENCES public.departments(department_id)
);
CREATE TABLE public.courses (
  course_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  subject_id integer NOT NULL,
  course_number character varying NOT NULL,
  course_level integer NOT NULL CHECK (course_level >= 0),
  course_title character varying NOT NULL,
  credit_hours numeric NOT NULL CHECK (credit_hours >= 0::numeric),
  course_description text,
  fall_offered boolean NOT NULL DEFAULT false,
  spring_offered boolean NOT NULL DEFAULT false,
  summer_offered boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  course_type USER-DEFINED NOT NULL DEFAULT 'STANDARD'::course_type,
  CONSTRAINT courses_pkey PRIMARY KEY (course_id),
  CONSTRAINT courses_subject_fk FOREIGN KEY (subject_id) REFERENCES public.subjects(subject_id)
);
CREATE TABLE public.course_rule_nodes (
  course_rule_node_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  target_course_id integer NOT NULL,
  parent_rule_node_id integer,
  requisite_type USER-DEFINED NOT NULL,
  node_type USER-DEFINED NOT NULL,
  rule_operator USER-DEFINED,
  required_course_id integer,
  required_count integer CHECK (required_count IS NULL OR required_count > 0),
  minimum_grade character varying,
  minimum_total_credits numeric CHECK (minimum_total_credits IS NULL OR minimum_total_credits >= 0::numeric),
  text_value text,
  source_text text,
  required_subject_id integer,
  minimum_course_level integer CHECK (minimum_course_level IS NULL OR minimum_course_level >= 0),
  minimum_standing USER-DEFINED,
  required_academic_program_id integer,
  CONSTRAINT course_rule_nodes_pkey PRIMARY KEY (course_rule_node_id),
  CONSTRAINT course_rule_target_course_fk FOREIGN KEY (target_course_id) REFERENCES public.courses(course_id),
  CONSTRAINT course_rule_parent_fk FOREIGN KEY (parent_rule_node_id) REFERENCES public.course_rule_nodes(course_rule_node_id),
  CONSTRAINT course_rule_required_course_fk FOREIGN KEY (required_course_id) REFERENCES public.courses(course_id),
  CONSTRAINT course_rule_required_subject_fk FOREIGN KEY (required_subject_id) REFERENCES public.subjects(subject_id),
  CONSTRAINT course_rule_required_academic_program_fk FOREIGN KEY (required_academic_program_id) REFERENCES public.academic_programs(academic_program_id)
);
CREATE TABLE public.academic_programs (
  academic_program_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  department_id integer NOT NULL,
  program_code character varying NOT NULL UNIQUE,
  program_name character varying NOT NULL,
  program_type USER-DEFINED NOT NULL,
  total_credit_hours numeric CHECK (total_credit_hours IS NULL OR total_credit_hours >= 0::numeric),
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT academic_programs_pkey PRIMARY KEY (academic_program_id),
  CONSTRAINT academic_programs_department_fk FOREIGN KEY (department_id) REFERENCES public.departments(department_id)
);
CREATE TABLE public.academic_program_relationships (
  academic_program_relationship_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  parent_program_id integer NOT NULL,
  child_program_id integer NOT NULL,
  relationship_type USER-DEFINED NOT NULL,
  CONSTRAINT academic_program_relationships_pkey PRIMARY KEY (academic_program_relationship_id),
  CONSTRAINT academic_program_relationship_parent_fk FOREIGN KEY (parent_program_id) REFERENCES public.academic_programs(academic_program_id),
  CONSTRAINT academic_program_relationship_child_fk FOREIGN KEY (child_program_id) REFERENCES public.academic_programs(academic_program_id)
);
CREATE TABLE public.requirement_sets (
  requirement_set_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  requirement_set_code character varying NOT NULL UNIQUE,
  requirement_set_name character varying NOT NULL,
  requirement_set_type USER-DEFINED NOT NULL,
  description text,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT requirement_sets_pkey PRIMARY KEY (requirement_set_id)
);
CREATE TABLE public.course_groups (
  course_group_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  course_group_code character varying NOT NULL UNIQUE,
  course_group_name character varying NOT NULL,
  course_group_type USER-DEFINED NOT NULL,
  description text,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT course_groups_pkey PRIMARY KEY (course_group_id)
);
CREATE TABLE public.course_group_courses (
  course_group_course_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  course_group_id integer NOT NULL,
  course_id integer NOT NULL,
  CONSTRAINT course_group_courses_pkey PRIMARY KEY (course_group_course_id),
  CONSTRAINT course_group_courses_group_fk FOREIGN KEY (course_group_id) REFERENCES public.course_groups(course_group_id),
  CONSTRAINT course_group_courses_course_fk FOREIGN KEY (course_id) REFERENCES public.courses(course_id)
);
CREATE TABLE public.requirement_nodes (
  requirement_node_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  requirement_set_id integer NOT NULL,
  parent_requirement_node_id integer,
  node_type USER-DEFINED NOT NULL,
  node_operator USER-DEFINED,
  node_name character varying,
  required_course_id integer,
  course_group_id integer,
  required_credit_hours numeric CHECK (required_credit_hours IS NULL OR required_credit_hours >= 0::numeric),
  required_count integer CHECK (required_count IS NULL OR required_count > 0),
  minimum_grade character varying,
  minimum_course_level integer CHECK (minimum_course_level IS NULL OR minimum_course_level >= 0),
  minimum_distinct_subjects integer CHECK (minimum_distinct_subjects IS NULL OR minimum_distinct_subjects > 0),
  display_order integer,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT requirement_nodes_pkey PRIMARY KEY (requirement_node_id),
  CONSTRAINT requirement_nodes_set_fk FOREIGN KEY (requirement_set_id) REFERENCES public.requirement_sets(requirement_set_id),
  CONSTRAINT requirement_nodes_parent_fk FOREIGN KEY (parent_requirement_node_id) REFERENCES public.requirement_nodes(requirement_node_id),
  CONSTRAINT requirement_nodes_course_fk FOREIGN KEY (required_course_id) REFERENCES public.courses(course_id),
  CONSTRAINT requirement_nodes_course_group_fk FOREIGN KEY (course_group_id) REFERENCES public.course_groups(course_group_id)
);
CREATE TABLE public.program_requirement_sets (
  program_requirement_set_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  academic_program_id integer NOT NULL,
  requirement_set_id integer NOT NULL,
  display_order integer,
  CONSTRAINT program_requirement_sets_pkey PRIMARY KEY (program_requirement_set_id),
  CONSTRAINT program_requirement_sets_program_fk FOREIGN KEY (academic_program_id) REFERENCES public.academic_programs(academic_program_id),
  CONSTRAINT program_requirement_sets_requirement_set_fk FOREIGN KEY (requirement_set_id) REFERENCES public.requirement_sets(requirement_set_id)
);
CREATE TABLE public.colleges (
  college_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  college_code character varying NOT NULL UNIQUE,
  college_name character varying NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT colleges_pkey PRIMARY KEY (college_id)
);
CREATE TABLE public.course_relations (
  course_relation_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  course_id integer NOT NULL,
  related_course_id integer NOT NULL,
  relation_type USER-DEFINED NOT NULL,
  is_bidirectional boolean NOT NULL DEFAULT true,
  maximum_combined_credits numeric,
  notes text,
  CONSTRAINT course_relations_pkey PRIMARY KEY (course_relation_id),
  CONSTRAINT course_relations_course_fk FOREIGN KEY (course_id) REFERENCES public.courses(course_id),
  CONSTRAINT course_relations_related_course_fk FOREIGN KEY (related_course_id) REFERENCES public.courses(course_id)
);