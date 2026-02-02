import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any
from html import unescape
import html2text

def clean_filename(filename: str) -> str:
    """
    Clean filename to be filesystem-safe
    """
    # Remove HTML tags and convert to plain text
    filename = re.sub(r"<[^>]+>", "", filename)
    # Replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Remove extra whitespace and truncate if too long
    filename = re.sub(r"\s+", "_", filename.strip())
    return filename[:100]  # Truncate to 100 chars


def html_to_markdown(html_content: str) -> str:
    """
    Convert HTML content to clean markdown
    """
    if not html_content:
        return ""

    # Initialize html2text converter
    h = html2text.html2text(html_content)

    # Clean up the markdown
    # Remove excessive newlines
    h = re.sub(r"\n{3,}", "\n\n", h)

    return h.strip()


def convert_pylon_to_kapa_format(input_file: str, output_dir: str = "pylon_tickets"):
    """
    Convert Pylon JSON export to Kapa.ai S3 storage format

    Args:
        input_file: Path to the Pylon JSON file
        output_dir: Directory to create the Kapa.ai format files
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Load the Pylon data
    with open(input_file, "r", encoding="utf-8") as f:
        pylon_data = json.load(f)

    tickets = pylon_data.get("tickets", [])
    metadata = pylon_data.get("metadata", {})

    print(f"Converting {len(tickets)} tickets to Kapa.ai format...")

    # Index for Kapa.ai
    index_data = []

    for i, ticket in enumerate(tickets, 1):
        try:
            # Extract ticket information
            issue_summary = ticket.get("issue_summary", {})
            issue_details = ticket.get("issue_details", {}).get("data", {})
            messages = ticket.get("messages", [])

            # Get basic ticket info
            ticket_id = issue_summary.get("id", f"unknown_{i}")
            ticket_number = issue_summary.get("number", i)
            title = issue_summary.get("title", f"Ticket {ticket_number}")
            state = issue_summary.get("state", "unknown")
            link = issue_summary.get("link", "")
            created_at = issue_summary.get("created_at", "")

            # Create filename
            filename = f"{ticket_number}_{clean_filename(title)}.md"
            filepath = os.path.join(output_dir, filename)

            # Build the markdown content
            markdown_content = []

            # Header
            markdown_content.append(f"# Support Ticket: {title} - {state.title()}")
            markdown_content.append("")

            # Metadata
            if created_at:
                markdown_content.append(f"**Created:** {created_at}")
            if link:
                markdown_content.append(f"**Pylon Link:** {link}")

            # Add custom fields if available
            custom_fields = issue_summary.get("custom_fields", {})
            if custom_fields:
                for field_name, field_data in custom_fields.items():
                    if isinstance(field_data, dict) and "values" in field_data:
                        values = field_data["values"]
                        if values:
                            markdown_content.append(
                                f"**{field_name.replace('_', ' ').title()}:** {', '.join(values)}"
                            )

            markdown_content.append("")
            markdown_content.append("---")
            markdown_content.append("")

            # Initial ticket body
            initial_body = issue_summary.get("body_html", "")
            if initial_body:
                markdown_content.append("## Initial Request")
                markdown_content.append("")
                markdown_content.append(html_to_markdown(initial_body))
                markdown_content.append("")

            # Process messages (conversation thread)
            if messages:
                markdown_content.append("## Conversation")
                markdown_content.append("")

                for msg_idx, message in enumerate(messages):
                    # Get message details
                    msg_html = message.get("message_html", "")
                    timestamp = message.get("timestamp", "")
                    author_info = message.get("author", {})
                    is_private = message.get("is_private", False)

                    # Determine author name
                    author_name = author_info.get("name", "Unknown")

                    # Determine if it's from customer or support team
                    if "contact" in author_info:
                        author_type = "Customer"
                    elif "user" in author_info:
                        author_type = "Support"
                    else:
                        author_type = "Unknown"

                    # Add message header
                    privacy_indicator = " (Private)" if is_private else ""
                    markdown_content.append(
                        f"### {author_type}: {author_name}{privacy_indicator}"
                    )
                    if timestamp:
                        markdown_content.append(f"*{timestamp}*")
                    markdown_content.append("")

                    # Add message content
                    if msg_html:
                        msg_markdown = html_to_markdown(msg_html)
                        markdown_content.append(msg_markdown)

                    # Add file attachments if any
                    file_urls = message.get("file_urls", [])
                    if file_urls:
                        markdown_content.append("")
                        markdown_content.append("**Attachments:**")
                        for file_url in file_urls:
                            markdown_content.append(f"- {file_url}")

                    markdown_content.append("")
                    markdown_content.append("---")
                    markdown_content.append("")

            # Write the markdown file
            full_markdown = "\n".join(markdown_content)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_markdown)

            # Add to index
            index_entry = {
                "file_path": filename,
                "title": f"Support Ticket #{ticket_number}: {title}",
                "url": link if link else None,
                "metadata": {
                    "ticket_id": ticket_id,
                    "ticket_number": ticket_number,
                    "state": state,
                    "created_at": created_at,
                    "total_messages": len(messages),
                    "source": "pylon_support_tickets",
                },
            }

            # Add custom fields to metadata
            if custom_fields:
                for field_name, field_data in custom_fields.items():
                    if isinstance(field_data, dict) and "values" in field_data:
                        index_entry["metadata"][field_name] = field_data["values"]

            index_data.append(index_entry)

            if i % 50 == 0:
                print(f"  Processed {i}/{len(tickets)} tickets...")

        except Exception as e:
            print(f"  Error processing ticket {i}: {str(e)}")
            continue

    # Create index.json
    index_json = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "source": "pylon_support_tickets",
        "total_documents": len(index_data),
        "original_metadata": metadata,
        "documents": index_data,
    }

    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_json, f, indent=2, ensure_ascii=False)

    # Create a summary file
    summary_path = os.path.join(output_dir, "conversion_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(
            f"""# Pylon to Kapa.ai Conversion Summary

## Conversion Details
- **Total Tickets Processed:** {len(index_data)}
- **Conversion Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Original Date Range:** {metadata.get('date_range', {}).get('start', 'Unknown')[:10]} to {metadata.get('date_range', {}).get('end', 'Unknown')[:10]}

## File Structure
- `index.json` - Kapa.ai compatible index file
- `*.md` - Individual ticket markdown files
- `conversion_summary.md` - This summary file

## Usage with Kapa.ai
1. Upload this entire folder to your S3 bucket
2. Configure Kapa.ai to use S3 storage pointing to your bucket
3. The `index.json` file will guide Kapa.ai to process all ticket documents

## Ticket Format
Each ticket includes:
- Support ticket header with title and state
- Initial request content
- Full conversation thread with timestamps
- Author identification (Customer vs Support)
- File attachments (where applicable)
- Metadata including ticket numbers and custom fields
"""
        )

    print(f"\n✅ Conversion completed!")
    print(f"📁 Output directory: {output_dir}")
    print(f"📄 Files created: {len(index_data)} markdown files + index.json")
    print(f"📋 Summary: See {summary_path}")

    return index_json


def main():
    """
    Main function to run the conversion
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pylon_to_kapa.py <pylon_json_file> [output_directory]")
        print(
            "Example: python pylon_to_kapa.py pylon_closed_tickets_20250603_164324.json pylon_tickets"
        )
        return

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "pylon_tickets"

    if not os.path.exists(input_file):
        print(f"❌ Error: Input file '{input_file}' not found")
        return

    try:
        convert_pylon_to_kapa_format(input_file, output_dir)
    except Exception as e:
        print(f"❌ Error during conversion: {str(e)}")


if __name__ == "__main__":
    main()
