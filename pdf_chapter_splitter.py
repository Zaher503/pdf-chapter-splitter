import PyPDF2
import os
import argparse
import re

def get_pdf_outline_info(outline, reader, current_level=2, max_level=0, parent_path=""):
    """
    Recursively extract the title, page number, and full path name of all bookmarks
    from a PDF outline.
    PyPDF2 page numbers are zero-based.
    current_level: the current bookmark depth level (1-based).
    max_level: the maximum depth level to process. 0 means all levels.
    parent_path: the full path name of the parent bookmark.
    """
    outline_info = []
    i = 0

    while i < len(outline):
        item = outline[i]

        if isinstance(item, PyPDF2.generic.Destination):
            try:
                title = item.title
                full_path_name = (
                    f"{parent_path} - {title}" if parent_path else title
                )
                page_index = reader.get_page_number(item.page)

                outline_info.append({
                    "title": title,
                    "page_index": page_index,
                    "full_path_name": full_path_name
                })

                # Check whether the next element is a child list of the current bookmark
                if (
                    i + 1 < len(outline)
                    and isinstance(outline[i + 1], list)
                ):
                    # If it is a child list and the depth level allows it, process recursively
                    if max_level == 0 or current_level < max_level:
                        sub_outline = outline[i + 1]
                        outline_info.extend(
                            get_pdf_outline_info(
                                sub_outline,
                                reader,
                                current_level + 1,
                                max_level,
                                full_path_name
                            )
                        )

                    # Skip the child list since it has already been processed
                    i += 1

            except Exception as e:
                print(
                    f"Warning: skipping an invalid bookmark "
                    f"'{getattr(item, 'title', 'Unknown title')}'. "
                    f"Error: {e}"
                )

        i += 1

    return outline_info

def calculate_page_ranges(outline_info, total_pages):
    """
    Calculate the page range corresponding to each bookmark based on the bookmark
    information and the total number of pages.
    The returned page numbers are 1-based.
    """
    sections = []

    # Sort bookmarks by page index to ensure correct order
    outline_info.sort(key=lambda x: x["page_index"])

    for i, item in enumerate(outline_info):
        title = item["title"]
        start_index = item["page_index"]

        # Default end page is the last page of the document (0-based)
        end_index = total_pages - 1
        if i + 1 < len(outline_info):
            # End page is the page before the next bookmark's start page
            end_index = outline_info[i + 1]["page_index"] - 1

        # Ensure the end page is not before the start page
        if start_index <= end_index:
            sections.append({
                "name": title,
                "full_path_name": item.get("full_path_name", title),
                "start_page": start_index + 1,  # Convert to 1-based
                "end_page": end_index + 1       # Convert to 1-based
            })
        elif i == len(outline_info) - 1:
            # If this is the last bookmark and start_index > end_index
            # (can happen if there is only one bookmark or it points to the last page)
            sections.append({
                "name": title,
                "full_path_name": item.get("full_path_name", title),
                "start_page": start_index + 1,
                "end_page": total_pages
            })

    return sections

def perform_pdf_split(reader, sections, output_dir, add_sequence=True, max_level=0):
    """
    Split the PDF into multiple files based on the calculated page ranges.
    max_level: the bookmark depth level to process. 0 means all levels.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving split PDF files to: {output_dir}")

    total_sections = len(sections)
    num_digits = len(str(total_sections))

    for i, section in enumerate(sections):
        writer = PyPDF2.PdfWriter()
        start_page_index = section["start_page"] - 1  # Convert to 0-based
        end_page_index = section["end_page"] - 1      # Convert to 0-based

        # Ensure the page range is valid
        if (
            start_page_index < 0
            or end_page_index >= len(reader.pages)
            or start_page_index > end_page_index
        ):
            print(
                f"Warning: skipping section with invalid page range "
                f"'{section.get('full_path_name', section['name'])}' "
                f"({section['start_page']}-{section['end_page']})"
            )
            continue

        for page_num in range(start_page_index, end_page_index + 1):
            writer.add_page(reader.pages[page_num])

        # Choose filename based on max_level
        if max_level != 1 and "full_path_name" in section:
            # When processing all levels (0) or more than one level (>1),
            # use the full path name
            name_to_clean = section["full_path_name"]
        else:
            # When only processing the first level (1),
            # or if full_path_name does not exist, use the original title
            name_to_clean = section["name"]

        # Remove invalid filename characters
        cleaned_name = re.sub(r'[\\/:*?"<>|]', "", name_to_clean)

        if add_sequence:
            sequence_prefix = f"{i + 1:0{num_digits}d}_"
            output_filename = f"{sequence_prefix}{cleaned_name}.pdf"
        else:
            output_filename = f"{cleaned_name}.pdf"

        output_filepath = os.path.join(output_dir, output_filename)

        with open(output_filepath, "wb") as output_pdf:
            writer.write(output_pdf)

        print(
            f"Created file: {output_filename}, "
            f"original pages: {section['start_page']}-{section['end_page']}"
        )

def split_pdf_by_chapters(pdf_path, output_dir=None, add_sequence=True, max_level=0):
    """
    Automatically split a PDF file based on its bookmarks.
    max_level: the bookmark depth level to process.
               0 means all levels, 1 means only the first level
               (default: 0, process all levels).
    """
    if not os.path.exists(pdf_path):
        print(f"Error: input file '{pdf_path}' does not exist.")
        return

    # Get the original PDF filename without extension
    pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]

    if output_dir is None:
        # If no output directory is specified, create a subfolder
        # in the same directory as the original PDF
        pdf_directory = os.path.dirname(pdf_path)
        final_output_dir = os.path.join(pdf_directory, pdf_basename)
    else:
        # If an output directory is specified, create a subfolder inside it
        final_output_dir = os.path.join(output_dir, pdf_basename)

    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            total_pages = len(reader.pages)
            print(f"Total number of pages in PDF: {total_pages}")

            outline = reader.outline
            if not outline:
                print(
                    "No bookmarks (outline) found in the PDF. "
                    "Cannot perform bookmark-based splitting."
                )
                return

            outline_info = get_pdf_outline_info(
                outline, reader, max_level=max_level
            )

            # Filter out bookmarks with None page numbers
            # (may point to external links, etc.)
            outline_info = [
                item for item in outline_info
                if item["page_index"] is not None
            ]

            if not outline_info:
                print(
                    "No valid bookmark information found. "
                    "Cannot perform bookmark-based splitting."
                )
                return

            sections = calculate_page_ranges(outline_info, total_pages)

            if not sections:
                print("No splittable sections were identified.")
                return

            perform_pdf_split(
                reader,
                sections,
                final_output_dir,
                add_sequence,
                max_level
            )
            print("\nPDF splitting completed!")

    except Exception as e:
        print(f"An error occurred while processing the PDF file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automatically split a PDF file based on its bookmarks."
    )
    parser.add_argument(
        "input_pdf",
        help="Path to the PDF file to be split."
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        default=None,  # Default value changed to None
        help=(
            "Output directory for the split PDF files "
            "(default: a subfolder in the same directory as the original PDF)."
        )
    )
    parser.add_argument(
        "--no-sequence",
        action="store_true",
        help="Do not add a sequence number prefix to the split files."
    )
    parser.add_argument(
        "--level",
        type=int,
        default=0,
        help=(
            "Bookmark depth level to process. "
            "0 means all levels, 1 means only the first level (default: 0)."
        )
    )

    args = parser.parse_args()

    split_pdf_by_chapters(
        args.input_pdf,
        args.output_dir,
        add_sequence=not args.no_sequence,
        max_level=args.level
    )