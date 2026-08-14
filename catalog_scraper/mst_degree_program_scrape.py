# ============================================================
# Missouri S&T Generic Catalog Section Scraper
# ============================================================
#
# PURPOSE
# -------
# Capture Missouri S&T catalog content faithfully for later
# interpretation by AI.
#
# The scraper DOES NOT attempt to determine:
#
#   - required courses
#   - elective groups
#   - AND / OR rules
#   - minor requirements
#   - emphasis requirements
#   - GPA rules
#   - degree requirements
#
# Instead, it preserves:
#
#   1. Complete selected-section HTML
#   2. Complete selected-section visible text
#   3. Headings
#   4. Links
#   5. Tables
#   6. Basic source metadata
#
# This allows a later AI step to interpret the requirements
# without the scraper making academic-rule assumptions.
#
# Output folder:
#
#   catalog_scraper/program_output/
#
# ============================================================


import requests
from bs4 import BeautifulSoup, Tag
import json
import os
import re
import hashlib

from urllib.parse import (
    urlparse,
    urljoin,
    parse_qs,
    unquote
)

# ============================================================
# URLS TO SCRAPE
# ============================================================

CATALOG_URLS = [

    # --------------------------------------------------------
    # Philosophy
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/philosophy/"
    "#minorstext",


    # --------------------------------------------------------
    # Physics
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/physics/"
    "#bachelorstext",

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/physics/"
    "#minorstext",


    # --------------------------------------------------------
    # Political Science
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/politicalscience/"
    "#minorstext",


    # --------------------------------------------------------
    # Pre-Health Professions
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/prehealthprofessions/"
    "#minortext",


    # --------------------------------------------------------
    # Psychology
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/psychology/"
    "#minorstext",


    # --------------------------------------------------------
    # Semiconductor Engineering
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/semiconductorengineering/"
    "#bachelorstext",


    # --------------------------------------------------------
    # Speech and Media Studies
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/speechandmediastudies/"
    "#minorstext",


    # --------------------------------------------------------
    # Systems Engineering
    # --------------------------------------------------------

    "https://catalog.mst.edu/undergraduate/"
    "degreeprogramsandcourses/systemsengineering/"
    "#minortext",
]


# ============================================================
# OUTPUT DIRECTORY
# ============================================================

SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

OUTPUT_FOLDER = os.path.join(
    SCRIPT_DIR,
    "program_output"
)

os.makedirs(
    OUTPUT_FOLDER,
    exist_ok=True
)


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; Missouri-ST-Catalog-Research/1.0)"
    )
}

REQUEST_TIMEOUT = 30


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    """
    Normalize whitespace while preserving wording.
    """

    if value is None:
        return None

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def element_text(element):
    """
    Extract normalized visible text.
    """

    if element is None:
        return None

    return clean_text(
        element.get_text(
            " ",
            strip=True
        )
    )


# ============================================================
# URL INFORMATION
# ============================================================

def parse_catalog_url(catalog_url):
    """
    Separate the page URL from the #fragment.

    Example:

    Input:
      https://catalog.mst.edu/.../biochemistry/#bachelorstext

    Output:
      page_url:
        https://catalog.mst.edu/.../biochemistry/

      fragment:
        bachelorstext
    """

    parsed = urlparse(
        catalog_url
    )

    fragment = (
        parsed.fragment.strip()
        if parsed.fragment
        else None
    )

    page_url = parsed._replace(
        fragment=""
    ).geturl()

    return page_url, fragment


def get_page_slug(page_url):
    """
    Get the final catalog path component.

    Example:

        .../biologicalsciences/
            -> biologicalsciences
    """

    path = urlparse(
        page_url
    ).path.rstrip("/")

    slug = path.split("/")[-1]

    return slug


# ============================================================
# COURSE LINK RESOLUTION
# ============================================================

def extract_course_code_from_url(url):
    """
    Resolve CourseLeaf course links when possible.

    Example:

        /search/?P=MATH%201211

    becomes:

        MATH 1211

    This is metadata only. The original HTML remains untouched.
    """

    if not url:
        return None

    try:

        parsed = urlparse(
            url
        )

        query = parse_qs(
            parsed.query
        )

        values = query.get(
            "P"
        )

        if not values:
            return None

        value = clean_text(
            unquote(
                values[0]
            )
        )

        if not re.search(
            r"\b\d{4}\b",
            value
        ):
            return None

        return value

    except Exception:

        return None


# ============================================================
# SECTION DETECTION
# ============================================================

def looks_like_navigation_only(element):
    """
    Determine whether an element appears to be only a tab/link
    rather than actual catalog content.
    """

    if element is None:
        return True

    text = (
        element_text(
            element
        )
        or ""
    )

    # Very short content is suspicious.
    if len(text) < 100:
        return True

    # Real content usually has paragraphs, tables, lists,
    # headings, etc.
    content_elements = element.find_all(
        [
            "p",
            "table",
            "ul",
            "ol",
            "h2",
            "h3",
            "h4"
        ]
    )

    if not content_elements:
        return True

    return False


def find_fragment_container(
    soup,
    fragment
):
    """
    Locate the content associated with a catalog fragment.

    The function intentionally tries several generic CourseLeaf
    conventions rather than assumptions about a specific degree.
    """

    if not fragment:
        return None, None


    # --------------------------------------------------------
    # STRATEGY 1
    #
    # CourseLeaf frequently uses:
    #
    # bachelorstextcontainer
    # minorstextcontainer
    # minortextcontainer
    # testtextcontainer
    #
    # --------------------------------------------------------

    possible_container_ids = [
        f"{fragment}container",
        fragment
    ]


    for container_id in possible_container_ids:

        candidate = soup.find(
            id=container_id
        )

        if (
            candidate is not None
            and not looks_like_navigation_only(
                candidate
            )
        ):

            return (
                candidate,
                f"id={container_id}"
            )


    # --------------------------------------------------------
    # STRATEGY 2
    #
    # Anchor:
    #
    # <a name="bachelorstext">
    #
    # Then inspect its parent.
    # --------------------------------------------------------

    anchor = soup.find(
        "a",
        attrs={
            "name": fragment
        }
    )

    if anchor is not None:

        parent = anchor.parent

        if (
            parent is not None
            and not looks_like_navigation_only(
                parent
            )
        ):

            return (
                parent,
                f"parent of anchor name={fragment}"
            )


    # --------------------------------------------------------
    # STRATEGY 3
    #
    # Any element whose ID contains the fragment.
    # --------------------------------------------------------

    candidates = soup.find_all(
        id=re.compile(
            re.escape(fragment),
            re.IGNORECASE
        )
    )


    viable_candidates = []


    for candidate in candidates:

        if looks_like_navigation_only(
            candidate
        ):
            continue

        text_length = len(
            element_text(
                candidate
            )
            or ""
        )

        viable_candidates.append(
            (
                text_length,
                candidate
            )
        )


    # Prefer the smallest useful container.
    #
    # This helps avoid selecting the entire page wrapper.

    if viable_candidates:

        viable_candidates.sort(
            key=lambda item: item[0]
        )

        candidate = (
            viable_candidates[0][1]
        )

        return (
            candidate,
            "generic fragment ID match"
        )


    return None, None


# ============================================================
# FULL-PAGE CONTENT DETECTION
# ============================================================

def find_primary_content(soup):
    """
    For URLs WITHOUT a #fragment, attempt to capture the primary
    catalog page content.

    This is needed for pages such as:

        /bioinformaticsminor/

    where the page itself represents the academic program.
    """

    # Common CourseLeaf/main-content IDs/classes.
    preferred_ids = [
        "content",
        "main",
        "maincontent",
        "textcontainer"
    ]


    for element_id in preferred_ids:

        candidate = soup.find(
            id=element_id
        )

        if (
            candidate is not None
            and not looks_like_navigation_only(
                candidate
            )
        ):

            return (
                candidate,
                f"primary content id={element_id}"
            )


    # HTML5 main element.
    candidate = soup.find(
        "main"
    )

    if (
        candidate is not None
        and not looks_like_navigation_only(
            candidate
        )
    ):

        return (
            candidate,
            "HTML <main> element"
        )


    # CourseLeaf content classes.
    class_candidates = soup.find_all(
        class_=re.compile(
            r"(page_content|pagecontent|maincontent|contentarea)",
            re.IGNORECASE
        )
    )


    viable = []


    for candidate in class_candidates:

        if looks_like_navigation_only(
            candidate
        ):
            continue

        text_length = len(
            element_text(
                candidate
            )
            or ""
        )

        viable.append(
            (
                text_length,
                candidate
            )
        )


    if viable:

        # For a full page, prefer the largest plausible
        # content region.

        viable.sort(
            key=lambda item: item[0],
            reverse=True
        )

        return (
            viable[0][1],
            "generic primary-content class"
        )


    # Final fallback:
    # body.
    #
    # This is intentionally conservative. It is better to retain
    # extra text than silently lose the academic requirements.

    body = soup.find(
        "body"
    )

    if body is not None:

        return (
            body,
            "fallback body capture"
        )


    raise RuntimeError(
        "Could not identify primary page content."
    )


# ============================================================
# CLEAN A COPY OF THE SELECTED HTML
# ============================================================

def create_clean_section(element):
    """
    Make a copy of the selected HTML and remove elements that
    carry no academic content.

    IMPORTANT:
    We do NOT aggressively remove divs/classes because doing so
    could accidentally remove catalog requirements.
    """

    section_soup = BeautifulSoup(
        str(element),
        "html.parser"
    )


    # Remove scripts/styles only.
    for unwanted in section_soup.find_all(
        [
            "script",
            "style",
            "noscript"
        ]
    ):

        unwanted.decompose()


    return section_soup


# ============================================================
# HEADINGS
# ============================================================

def extract_headings(section):
    """
    Preserve headings in source order.
    """

    headings = []


    for index, heading in enumerate(
        section.find_all(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6"
            ]
        ),
        start=1
    ):

        text = element_text(
            heading
        )

        if not text:
            continue


        headings.append({
            "number":
                index,

            "level":
                heading.name,

            "text":
                text,

            "id":
                heading.get("id")
        })


    return headings


# ============================================================
# LINKS
# ============================================================

def extract_links(
    section,
    page_url
):
    """
    Preserve every link in the captured section.
    """

    links = []


    for index, link in enumerate(
        section.find_all(
            "a",
            href=True
        ),
        start=1
    ):

        href = link.get(
            "href"
        )

        absolute = urljoin(
            page_url,
            href
        )

        links.append({
            "number":
                index,

            "text":
                element_text(link),

            "href":
                href,

            "url":
                absolute,

            "resolved_course":
                extract_course_code_from_url(
                    absolute
                )
        })


    return links


# ============================================================
# TABLES
# ============================================================

def extract_tables(
    section,
    page_url
):
    """
    Preserve tables without interpreting their academic meaning.
    """

    tables = []


    for table_number, table in enumerate(
        section.find_all("table"),
        start=1
    ):

        rows = []


        for row_number, row in enumerate(
            table.find_all("tr"),
            start=1
        ):

            cells = row.find_all(
                ["th", "td"],
                recursive=False
            )


            if not cells:

                cells = row.find_all(
                    ["th", "td"]
                )


            if not cells:
                continue


            row_data = []


            for column_number, cell in enumerate(
                cells,
                start=1
            ):

                links = []


                for link in cell.find_all(
                    "a",
                    href=True
                ):

                    href = link.get(
                        "href"
                    )

                    absolute = urljoin(
                        page_url,
                        href
                    )

                    links.append({
                        "text":
                            element_text(
                                link
                            ),

                        "url":
                            absolute,

                        "resolved_course":
                            extract_course_code_from_url(
                                absolute
                            )
                    })


                row_data.append({
                    "column":
                        column_number,

                    "tag":
                        cell.name,

                    "text":
                        element_text(
                            cell
                        ),

                    "colspan":
                        cell.get(
                            "colspan"
                        ),

                    "rowspan":
                        cell.get(
                            "rowspan"
                        ),

                    "links":
                        links
                })


            rows.append({
                "row":
                    row_number,

                "cells":
                    row_data
            })


        tables.append({
            "table_number":
                table_number,

            "text":
                element_text(
                    table
                ),

            "rows":
                rows,

            # Preserve original table HTML too.
            "html":
                str(table)
        })


    return tables


# ============================================================
# CONTENT INVENTORY
# ============================================================

def create_inventory(
    section,
    text,
    html,
    headings,
    links,
    tables
):
    """
    Basic integrity information.

    These are NOT academic interpretations.
    They simply help us identify suspicious/empty scrapes.
    """

    return {

        "text_character_count":
            len(text),

        "html_character_count":
            len(html),

        "heading_count":
            len(headings),

        "paragraph_count":
            len(
                section.find_all("p")
            ),

        "list_count":
            len(
                section.find_all(
                    ["ul", "ol"]
                )
            ),

        "table_count":
            len(tables),

        "link_count":
            len(links),

        "superscript_count":
            len(
                section.find_all("sup")
            ),

        "text_sha256":
            hashlib.sha256(
                text.encode(
                    "utf-8"
                )
            ).hexdigest(),

        "html_sha256":
            hashlib.sha256(
                html.encode(
                    "utf-8"
                )
            ).hexdigest()
    }


# ============================================================
# SCRAPE ONE URL
# ============================================================

def scrape_catalog_url(
    catalog_url
):
    """
    Scrape one Missouri S&T catalog URL.
    """

    print("\n" + "=" * 78)
    print("SCRAPING")
    print("=" * 78)

    print(
        catalog_url
    )


    # --------------------------------------------------------
    # Parse URL
    # --------------------------------------------------------

    page_url, fragment = (
        parse_catalog_url(
            catalog_url
        )
    )

    page_slug = get_page_slug(
        page_url
    )


    print(
        "\nPage URL:",
        page_url
    )

    print(
        "Fragment:",
        fragment
        if fragment
        else "(none)"
    )


    # --------------------------------------------------------
    # Download page
    # --------------------------------------------------------

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()


    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Downloaded:",
        f"{len(response.text):,}",
        "HTML characters"
    )


    # --------------------------------------------------------
    # Parse page
    # --------------------------------------------------------

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    # --------------------------------------------------------
    # Locate requested content
    # --------------------------------------------------------

    if fragment:

        selected_element, selection_method = (
            find_fragment_container(
                soup,
                fragment
            )
        )


        if selected_element is None:

            raise RuntimeError(
                f"Could not locate catalog section "
                f"#{fragment} on {page_url}"
            )


        capture_type = (
            "fragment_section"
        )


    else:

        selected_element, selection_method = (
            find_primary_content(
                soup
            )
        )

        capture_type = (
            "full_program_page"
        )


    # --------------------------------------------------------
    # Create minimally cleaned copy
    # --------------------------------------------------------

    section = create_clean_section(
        selected_element
    )


    # --------------------------------------------------------
    # Preserve text and HTML
    # --------------------------------------------------------

    section_text = (
        element_text(
            section
        )
        or ""
    )

    section_html = str(
        section
    )


    # --------------------------------------------------------
    # Lightweight structural extraction
    # --------------------------------------------------------

    headings = extract_headings(
        section
    )

    links = extract_links(
        section,
        page_url
    )

    tables = extract_tables(
        section,
        page_url
    )


    # --------------------------------------------------------
    # Inventory
    # --------------------------------------------------------

    inventory = create_inventory(
        section,
        section_text,
        section_html,
        headings,
        links,
        tables
    )


    # --------------------------------------------------------
    # Page title
    # --------------------------------------------------------

    title = None

    if soup.title:

        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )


    # --------------------------------------------------------
    # Build JSON
    # --------------------------------------------------------

    output_data = {

        "source": {

            "institution":
                "Missouri University of Science and Technology",

            "catalog_url":
                catalog_url,

            "page_url":
                page_url,

            "fragment":
                fragment,

            "page_slug":
                page_slug,

            "page_title":
                title,

            "capture_type":
                capture_type,

            "selection_method":
                selection_method
        },


        # ----------------------------------------------------
        # Integrity / debugging information
        # ----------------------------------------------------

        "inventory":
            inventory,


        # ----------------------------------------------------
        # Convenience structures
        #
        # These do NOT replace the source HTML/text.
        # ----------------------------------------------------

        "headings":
            headings,

        "links":
            links,

        "tables":
            tables,


        # ----------------------------------------------------
        # PRIMARY AI SOURCE MATERIAL
        # ----------------------------------------------------

        "section_text":
            section_text,

        "section_html":
            section_html
    }


    # --------------------------------------------------------
    # Output filename
    # --------------------------------------------------------

    section_name = (
        fragment
        if fragment
        else "fullpage"
    )

    filename = (
        f"{page_slug}_{section_name}.json"
    )


    output_file = os.path.join(
        OUTPUT_FOLDER,
        filename
    )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output_data,
            file,
            indent=4,
            ensure_ascii=False
        )


    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print(
        "\nSelection:",
        selection_method
    )

    print(
        "Text characters:",
        f"{inventory['text_character_count']:,}"
    )

    print(
        "HTML characters:",
        f"{inventory['html_character_count']:,}"
    )

    print(
        "Headings:",
        inventory["heading_count"]
    )

    print(
        "Paragraphs:",
        inventory["paragraph_count"]
    )

    print(
        "Tables:",
        inventory["table_count"]
    )

    print(
        "Links:",
        inventory["link_count"]
    )

    print(
        "\nSaved:"
    )

    print(
        output_file
    )


    return {
        "catalog_url":
            catalog_url,

        "output_file":
            output_file,

        "success":
            True,

        "error":
            None
    }


# ============================================================
# SCRAPE ALL URLS
# ============================================================

results = []


print("\n" + "=" * 78)
print("MISSOURI S&T GENERIC CATALOG SCRAPER")
print("=" * 78)

print(
    "\nURLs to process:",
    len(CATALOG_URLS)
)


for catalog_url in CATALOG_URLS:

    try:

        result = scrape_catalog_url(
            catalog_url
        )

        results.append(
            result
        )


    except Exception as error:

        print(
            "\nERROR:"
        )

        print(
            str(error)
        )

        results.append({
            "catalog_url":
                catalog_url,

            "output_file":
                None,

            "success":
                False,

            "error":
                str(error)
        })


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 78)
print("FINAL SUMMARY")
print("=" * 78)


successful = sum(
    1
    for result in results
    if result["success"]
)

failed = (
    len(results)
    - successful
)


print(
    "\nSuccessful:",
    successful
)

print(
    "Failed:",
    failed
)


for result in results:

    status = (
        "OK"
        if result["success"]
        else "FAILED"
    )

    print(
        f"\n[{status}] "
        f"{result['catalog_url']}"
    )

    if result["output_file"]:

        print(
            "   ->",
            result["output_file"]
        )

    if result["error"]:

        print(
            "   Error:",
            result["error"]
        )


print("\nDone.")