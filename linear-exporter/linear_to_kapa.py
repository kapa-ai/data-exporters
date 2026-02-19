import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any


def clean_filename(filename: str) -> str:
    """
    Clean filename to be filesystem-safe
    """
    # Remove HTML tags if any
    filename = re.sub(r"<[^>]+>", "", filename)
    # Replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Remove extra whitespace and truncate
    filename = re.sub(r"\s+", "_", filename.strip())
    return filename[:100]


def format_timestamp(iso_str: str) -> str:
    """
    Convert ISO timestamp to a readable format: 2026-02-17 16:29 UTC
    """
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str


def convert_linear_to_kapa_format(input_file: str, output_dir: str = "linear_tickets"):
    """
    Convert Linear JSON export to Kapa.ai S3 storage format.

    Follows the Kapa markdown best practices:
      - Proper heading hierarchy (# Title, ## Section, ### Subsection)
      - Bold metadata fields with readable timestamps
      - Conversation-style comment layout

    And the Kapa index.json format:
      - Flat JSON array of {object_key, source_url} entries

    See: https://docs.kapa.ai/data-sources/faq#how-should-i-format-markdown-files-for-ai-ingestion
    See: https://docs.kapa.ai/data-sources/s3-storage#best-practices
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Load the Linear data
    with open(input_file, "r", encoding="utf-8") as f:
        linear_data = json.load(f)

    tickets = linear_data.get("tickets", [])

    print(f"Converting {len(tickets)} tickets to Kapa.ai format...")

    # Kapa index: flat array of {object_key, source_url}
    index_data: List[Dict[str, str]] = []

    for i, ticket in enumerate(tickets, 1):
        try:
            issue = ticket.get("issue", {})
            comments = ticket.get("comments", [])

            # Basic issue info
            identifier = issue.get("identifier", f"ISSUE-{i}")
            number = issue.get("number", i)
            title = issue.get("title", f"Issue {number}")
            description = issue.get("description", "")
            url = issue.get("url", "")
            created_at = issue.get("createdAt", "")
            completed_at = issue.get("completedAt", "")
            priority_label = issue.get("priorityLabel", "")

            # State info
            state_info = issue.get("state", {})
            state_name = state_info.get("name", "Unknown")

            # Team info
            team_info = issue.get("team", {})
            team_name = team_info.get("name", "")

            # Assignee / Creator
            assignee = issue.get("assignee", {}) or {}
            creator = issue.get("creator", {}) or {}

            # Labels
            labels_data = issue.get("labels", {}).get("nodes", [])
            label_names = [l.get("name", "") for l in labels_data if l.get("name")]

            # Project / Cycle
            project = issue.get("project", {}) or {}
            cycle = issue.get("cycle", {}) or {}

            # Create filename
            filename = f"{identifier}_{clean_filename(title)}.md"
            filepath = os.path.join(output_dir, filename)

            # ── Build markdown following Kapa best practices ──
            # Modelled after the support ticket example in:
            # https://docs.kapa.ai/data-sources/faq#how-should-i-format-markdown-files-for-ai-ingestion
            md = []

            # H1 — ticket header
            md.append(f"# Linear Issue: {identifier} — {title}")
            md.append("")

            # Metadata as bold key-value pairs (Kapa recommended style)
            md.append(f"**Timestamp**: {format_timestamp(created_at)}")
            md.append("")
            md.append(f"**Status**: {state_name}")
            md.append("")
            if completed_at:
                md.append(f"**Completed**: {format_timestamp(completed_at)}")
                md.append("")
            if team_name:
                md.append(f"**Team**: {team_name}")
                md.append("")
            if priority_label:
                md.append(f"**Priority**: {priority_label}")
                md.append("")
            if assignee.get("name"):
                md.append(f"**Assignee**: {assignee['name']}")
                md.append("")
            if creator.get("name"):
                md.append(f"**Creator**: {creator['name']}")
                md.append("")
            if label_names:
                md.append(f"**Tags**: {', '.join(label_names)}")
                md.append("")
            if project.get("name"):
                md.append(f"**Project**: {project['name']}")
                md.append("")
            if cycle.get("name"):
                md.append(f"**Cycle**: {cycle['name']} (#{cycle.get('number', '')})")
                md.append("")

            # H2 — Issue description
            md.append("## Issue description")
            md.append("")
            if description:
                md.append(description)
            else:
                md.append("No description provided.")
            md.append("")

            # H2 — Conversation (comments)
            if comments:
                md.append("## Conversation")
                md.append("")

                for comment in comments:
                    comment_body = comment.get("body", "")
                    comment_created = comment.get("createdAt", "")
                    comment_user = comment.get("user", {}) or {}
                    bot_actor = comment.get("botActor", {}) or {}

                    # Determine author
                    if bot_actor.get("name"):
                        author_name = f"{bot_actor['name']} (Bot)"
                    elif comment_user.get("name"):
                        author_name = comment_user["name"]
                    else:
                        author_name = "Unknown"

                    # Each comment as bold author + timestamp, then body
                    md.append(f"**{author_name}**: {comment_body if comment_body else '_No body content._'}")
                    md.append("")

            # Write the markdown file
            full_markdown = "\n".join(md)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_markdown)

            # Add to Kapa index (flat format: object_key + source_url)
            if url:
                index_data.append({
                    "object_key": filename,
                    "source_url": url,
                })

            if i % 50 == 0:
                print(f"  Processed {i}/{len(tickets)} tickets...")

        except Exception as e:
            print(f"  Error processing ticket {i}: {str(e)}")
            continue

    # Write index.json — flat array as required by Kapa
    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Conversion completed!")
    print(f"📁 Output directory: {output_dir}")
    print(f"📄 Files created: {len(tickets)} markdown files + index.json")

    return index_data


def main():
    """
    Main function to run the conversion
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python linear_to_kapa.py <linear_json_file> [output_directory]")
        print(
            "Example: python linear_to_kapa.py linear_closed_tickets_20250603_164324.json linear_tickets"
        )
        return

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "linear_tickets"

    if not os.path.exists(input_file):
        print(f"❌ Error: Input file '{input_file}' not found")
        return

    try:
        convert_linear_to_kapa_format(input_file, output_dir)
    except Exception as e:
        print(f"❌ Error during conversion: {str(e)}")


if __name__ == "__main__":
    main()
