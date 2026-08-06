# Import libraries for requesting and reading the catalog webpages
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin

# Missouri S&T course list page
COURSE_LIST_URL = "https://catalog.mst.edu/undergraduate/courselist/"

# Subjects that we want to scrape
subjects = [
    {"subject_id": 1, "department_id": 1, "subject_code": "THEATRE", "subject_name": "Theatre"},
    {"subject_id": 2, "department_id": 1, "subject_code": "SPANISH", "subject_name": "Spanish"},
    {"subject_id": 3, "department_id": 1, "subject_code": "RUSSIAN", "subject_name": "Russian"},
    {"subject_id": 4, "department_id": 1, "subject_code": "PHILOS", "subject_name": "Philosophy"},
    {"subject_id": 5, "department_id": 1, "subject_code": "MUSIC", "subject_name": "Music"},
    {"subject_id": 6, "department_id": 1, "subject_code": "GERMAN", "subject_name": "German"},
    {"subject_id": 7, "department_id": 1, "subject_code": "FRENCH", "subject_name": "French"},
    {"subject_id": 8, "department_id": 1, "subject_code": "ETYM", "subject_name": "Etymology"},
    {"subject_id": 9, "department_id": 1, "subject_code": "ART", "subject_name": "Art"},
    {"subject_id": 10, "department_id": 2, "subject_code": "BIO SCI", "subject_name": "Biological Sciences"},
    {"subject_id": 11, "department_id": 3, "subject_code": "CHEM", "subject_name": "Chemistry"},
    {"subject_id": 12, "department_id": 4, "subject_code": "EDUC", "subject_name": "Education"},
    {"subject_id": 13, "department_id": 5, "subject_code": "TCH COM", "subject_name": "Technical Communication"},
    {"subject_id": 14, "department_id": 5, "subject_code": "SP&M S", "subject_name": "Speech & Media Studies"},
    {"subject_id": 15, "department_id": 5, "subject_code": "ENGLISH", "subject_name": "English"},
    {"subject_id": 16, "department_id": 6, "subject_code": "ENV SCI", "subject_name": "Environmental Science"},
    {"subject_id": 17, "department_id": 7, "subject_code": "POL SCI", "subject_name": "Political Science"},
    {"subject_id": 18, "department_id": 7, "subject_code": "HISTORY", "subject_name": "History"},
    {"subject_id": 19, "department_id": 8, "subject_code": "STAT", "subject_name": "Statistics"},
    {"subject_id": 20, "department_id": 8, "subject_code": "MATH", "subject_name": "Mathematics"},
    {"subject_id": 21, "department_id": 9, "subject_code": "PHYSICS", "subject_name": "Physics"},
    {"subject_id": 22, "department_id": 10, "subject_code": "PSYCH", "subject_name": "Psychology"},
    {"subject_id": 23, "department_id": 11, "subject_code": "CHEM ENG", "subject_name": "Chemical Engineering"},
    {"subject_id": 24, "department_id": 11, "subject_code": "BME", "subject_name": "Biomedical Engineering"},
    {"subject_id": 25, "department_id": 12, "subject_code": "ENV ENG", "subject_name": "Environmental Engineering"},
    {"subject_id": 26, "department_id": 12, "subject_code": "CIV ENG", "subject_name": "Civil Engineering"},
    {"subject_id": 27, "department_id": 12, "subject_code": "ARCH ENG", "subject_name": "Architectural Engineering"},
    {"subject_id": 28, "department_id": 13, "subject_code": "COMP SCI", "subject_name": "Computer Science"},
    {"subject_id": 29, "department_id": 14, "subject_code": "ELEC ENG", "subject_name": "Electrical Engineering"},
    {"subject_id": 30, "department_id": 14, "subject_code": "COMP ENG", "subject_name": "Computer Engineering"},
    {"subject_id": 31, "department_id": 15, "subject_code": "PET ENG", "subject_name": "Petroleum Engineering"},
    {"subject_id": 32, "department_id": 15, "subject_code": "GEOPHYS", "subject_name": "Geophysics"},
    {"subject_id": 33, "department_id": 15, "subject_code": "GEOLOGY", "subject_name": "Geology"},
    {"subject_id": 34, "department_id": 15, "subject_code": "GEO ENG", "subject_name": "Geological Engineering"},
    {"subject_id": 35, "department_id": 16, "subject_code": "SEMI ENG", "subject_name": "Semiconductor Engineering"},
    {"subject_id": 36, "department_id": 16, "subject_code": "MET ENG", "subject_name": "Metallurgical Engineering"},
    {"subject_id": 37, "department_id": 16, "subject_code": "MS&E", "subject_name": "Materials Science & Eng"},
    {"subject_id": 38, "department_id": 16, "subject_code": "CER ENG", "subject_name": "Ceramic Engineering"},
    {"subject_id": 39, "department_id": 17, "subject_code": "MECH ENG", "subject_name": "Mechanical Engineering"},
    {"subject_id": 40, "department_id": 17, "subject_code": "AERO ENG", "subject_name": "Aerospace Engineering"},
    {"subject_id": 41, "department_id": 18, "subject_code": "MIN ENG", "subject_name": "Mining Engineering"},
    {"subject_id": 42, "department_id": 18, "subject_code": "EXP ENG", "subject_name": "Explosives Engineering"},
    {"subject_id": 43, "department_id": 19, "subject_code": "NUC ENG", "subject_name": "Nuclear Engineering"},
    {"subject_id": 44, "department_id": 20, "subject_code": "MKT", "subject_name": "Marketing"},
    {"subject_id": 45, "department_id": 20, "subject_code": "IS&T", "subject_name": "Info Science & Technology"},
    {"subject_id": 46, "department_id": 20, "subject_code": "FINANCE", "subject_name": "Finance"},
    {"subject_id": 47, "department_id": 20, "subject_code": "ERP", "subject_name": "Enterprise Resource Planning"},
    {"subject_id": 48, "department_id": 20, "subject_code": "BUS", "subject_name": "Business"},
    {"subject_id": 49, "department_id": 21, "subject_code": "ECON", "subject_name": "Economics"},
    {"subject_id": 50, "department_id": 22, "subject_code": "SYS ENG", "subject_name": "Systems Engineering"},
    {"subject_id": 51, "department_id": 22, "subject_code": "ENG MGT", "subject_name": "Engineering Management"},
    {"subject_id": 52, "department_id": 23, "subject_code": "FR ENG", "subject_name": "Freshman Engineering"},
    {"subject_id": 53, "department_id": 24, "subject_code": "PREMED", "subject_name": "Pre-Medicine"},
    {"subject_id": 54, "department_id": 1, "subject_code": "ALP", "subject_name": "Arts, Languages & Philosophy"},
]

# Create output folder
os.makedirs("output", exist_ok=True)

# Request the official Missouri S&T course list
response = requests.get(COURSE_LIST_URL)
response.raise_for_status()

# Parse the course list
soup = BeautifulSoup(response.text, "html.parser")

# Build a dictionary of subject code -> official URL
catalog_links = {}

for link in soup.find_all("a", href=True):

    text = link.get_text(" ", strip=True)

    # Course List entries look like:
    # Theatre (THEATRE)
    # Computer Science (COMP SCI)
    match = re.search(r"\(([^()]+)\)\s*$", text)

    if match:
        subject_code = match.group(1).strip()

        catalog_links[subject_code] = urljoin(
            COURSE_LIST_URL,
            link["href"]
        )

# Loop through our selected subjects
for subject in subjects:

    subject_id = subject["subject_id"]
    department_id = subject["department_id"]
    subject_code = subject["subject_code"]
    subject_name = subject["subject_name"]

    print(f"\nProcessing {subject_name} ({subject_code})...")

    # Find the official catalog URL using the subject code
    url = catalog_links.get(subject_code)

    #Special case for ALP
    if subject_code == "ALP":
        url = "https://catalog.mst.edu/undergraduate/degreeprogramsandcourses/artslanguagesandphilosophy/"

    # Create safe filename
    filename = re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        subject_name.lower()
    ).strip("_")

    output_file = f"output/{filename}_courses.json"

    # If subject does not exist in the official course list
    if not url:

        print(f"WARNING: No catalog page found for {subject_code}")

        # Still create an empty JSON file
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump([], file, indent=4, ensure_ascii=False)

        continue

    try:

        # Request the subject webpage
        response = requests.get(url)
        response.raise_for_status()

        # Parse subject webpage
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all course blocks
        course_blocks = soup.find_all(
            "div",
            class_="courseblock"
        )

        courses = []

        # Extract courses
        for course in course_blocks:

            title_element = course.find(
                class_="courseblocktitle"
            )

            description_element = course.find(
                class_="courseblockdesc"
            )

            title = (
                title_element.get_text(" ", strip=True)
                if title_element
                else None
            )

            description = (
                description_element.get_text(" ", strip=True)
                if description_element
                else None
            )

            courses.append({
                "subject_id": subject_id,
                "department_id": department_id,
                "subject_code": subject_code,
                "subject_name": subject_name,
                "course": title,
                "description": description
            })

        # Save subject JSON file
        with open(output_file, "w", encoding="utf-8") as file:

            json.dump(
                courses,
                file,
                indent=4,
                ensure_ascii=False
            )

        print(f"URL: {url}")
        print(f"Courses found: {len(courses)}")
        print(f"Saved: {output_file}")

    except requests.RequestException as error:

        print(f"ERROR processing {subject_name}: {error}")

# Finished
print("\nAll subjects completed.")