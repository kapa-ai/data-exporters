import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


class PylonAPIClient:
    def __init__(self, api_token: str):
        """
        Initialize Pylon API client

        Args:
            api_token: Your Pylon API token (keep this secure!)
        """
        self.api_token = api_token
        self.base_url = "https://api.usepylon.com"
        self.headers = {
            "Authorization": f"Bearer <TOKEN>",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_issues_in_range(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get issues using the direct GET endpoint with time range

        Args:
            start_time: Start time for the range (max 30 days from end_time)
            end_time: End time for the range

        Returns:
            List of issues in the specified time range
        """
        # Format dates as RFC3339
        start_str = start_time.isoformat() + "Z"
        end_str = end_time.isoformat() + "Z"

        # Use the GET endpoint with time range parameters
        params = {"start_time": start_str, "end_time": end_str}

        response = requests.get(
            f"{self.base_url}/issues", headers=self.headers, params=params
        )

        if response.status_code != 200:
            raise Exception(
                f"API request failed: {response.status_code} - {response.text}"
            )

        return response.json().get("data", [])

    def search_closed_issues_only(self) -> List[Dict[str, Any]]:
        """
        Search for closed issues using the search endpoint with just state filter

        Returns:
            List of closed issues
        """
        search_payload = {
            "filter": {"field": "state", "operator": "equals", "value": "closed"},
            "limit": 100,
        }

        all_issues = []
        cursor = None

        while True:
            if cursor:
                search_payload["cursor"] = cursor

            response = requests.post(
                f"{self.base_url}/issues/search",
                headers=self.headers,
                json=search_payload,
            )

            if response.status_code != 200:
                raise Exception(
                    f"API request failed: {response.status_code} - {response.text}"
                )

            result = response.json()
            issues = result.get("data", [])

            if not issues:
                break

            all_issues.extend(issues)

            # Check for next page
            cursor = result.get("meta", {}).get("cursor")
            if not cursor:
                break

        return all_issues

    def get_issue_details(self, issue_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific issue

        Args:
            issue_id: The ID of the issue to fetch

        Returns:
            Detailed issue information
        """
        response = requests.get(
            f"{self.base_url}/issues/{issue_id}", headers=self.headers
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch issue {issue_id}: {response.status_code} - {response.text}"
            )

        return response.json()

    def get_issue_messages(self, issue_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a specific issue

        Args:
            issue_id: The ID of the issue

        Returns:
            List of messages for the issue
        """
        response = requests.get(
            f"{self.base_url}/issues/{issue_id}/messages", headers=self.headers
        )

        if response.status_code != 200:
            print(
                f"Warning: Failed to fetch messages for issue {issue_id}: {response.status_code}"
            )
            return []

        return response.json().get("data", [])

    def filter_issues_by_date_and_state(
        self,
        issues: List[Dict],
        start_date: datetime,
        end_date: datetime,
        state: str = "closed",
    ) -> List[Dict]:
        """
        Filter issues by date range and state

        Args:
            issues: List of issues to filter
            start_date: Start date for filtering
            end_date: End date for filtering
            state: State to filter by

        Returns:
            Filtered list of issues
        """
        filtered_issues = []

        for issue in issues:
            # Check state
            if issue.get("state") != state:
                continue

            # Check date - try multiple date fields
            issue_date = None
            for date_field in ["created_at", "updated_at", "closed_at"]:
                if date_field in issue and issue[date_field]:
                    try:
                        # Parse the date string
                        date_str = issue[date_field].replace("Z", "+00:00")
                        issue_date = datetime.fromisoformat(date_str.replace("Z", ""))
                        break
                    except:
                        continue

            if issue_date and start_date <= issue_date <= end_date:
                filtered_issues.append(issue)

        return filtered_issues

    def fetch_all_closed_tickets(self, days_back: int = 180) -> Dict[str, Any]:
        """
        Fetch all closed tickets from the last N days with complete metadata and messages

        Args:
            days_back: Number of days to look back (default: 90)

        Returns:
            Complete dataset of closed tickets with all metadata and messages
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        print(
            f"Fetching closed tickets from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

        # First, try to get all closed issues using the search endpoint
        print("Fetching all closed issues...")
        try:
            all_closed_issues = self.search_closed_issues_only()
            print(f"Found {len(all_closed_issues)} total closed issues")

            # Filter by date range
            filtered_issues = self.filter_issues_by_date_and_state(
                all_closed_issues, start_date, end_date, "closed"
            )
            print(f"Filtered to {len(filtered_issues)} closed issues in date range")

        except Exception as e:
            print(f"Search method failed: {e}")
            print("Trying alternative approach with time-based chunks...")

            # Alternative: fetch in 30-day chunks
            filtered_issues = []
            current_end = end_date

            while current_end > start_date:
                current_start = max(start_date, current_end - timedelta(days=30))

                print(
                    f"Fetching issues from {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}"
                )

                try:
                    chunk_issues = self.get_issues_in_range(current_start, current_end)
                    closed_in_chunk = [
                        issue
                        for issue in chunk_issues
                        if issue.get("state") == "closed"
                    ]
                    filtered_issues.extend(closed_in_chunk)
                    print(f"  Found {len(closed_in_chunk)} closed issues in this chunk")
                except Exception as chunk_error:
                    print(f"  Error fetching chunk: {chunk_error}")

                current_end = current_start

        print(f"\nProcessing {len(filtered_issues)} closed tickets...")

        # Now get detailed information for each issue
        all_tickets = []

        for i, issue in enumerate(filtered_issues, 1):
            issue_id = issue.get("id")
            if not issue_id:
                continue

            try:
                print(f"  Processing ticket {i}/{len(filtered_issues)}: {issue_id}")

                # Get detailed issue information
                detailed_issue = self.get_issue_details(issue_id)

                # Get all messages for this issue
                messages = self.get_issue_messages(issue_id)

                # Combine all data
                complete_ticket = {
                    "issue_summary": issue,
                    "issue_details": detailed_issue,
                    "messages": messages,
                    "total_messages": len(messages),
                }

                all_tickets.append(complete_ticket)
                print(f"    ✓ Processed ({len(messages)} messages)")

            except Exception as e:
                print(f"    ✗ Error processing ticket {issue_id}: {str(e)}")
                continue

        result = {
            "metadata": {
                "total_tickets": len(all_tickets),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "fetched_at": datetime.now().isoformat(),
                "days_back": days_back,
            },
            "tickets": all_tickets,
        }

        print(
            f"\n✅ Successfully fetched {len(all_tickets)} closed tickets with full data"
        )
        return result


def main():
    """
    Main function to demonstrate usage
    """
    # IMPORTANT: Replace with your NEW API token (after revoking the old one)
    API_TOKEN = "XXX"

    # Initialize the client
    client = PylonAPIClient(API_TOKEN)

    try:
        # Test API connection first
        print("Testing API connection...")
        test_response = requests.get(f"{client.base_url}/me", headers=client.headers)

        if test_response.status_code != 200:
            raise Exception(
                f"API authentication failed: {test_response.status_code} - {test_response.text}"
            )

        print("✅ API connection successful")
        org_data = test_response.json()
        print(f"Organization: {org_data.get('data', {}).get('name', 'Unknown')}")

        # Fetch all closed tickets from last 90 days
        all_data = client.fetch_all_closed_tickets(days_back=180)

        # Save to JSON file
        output_filename = (
            f"pylon_closed_tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Data saved to: {output_filename}")
        print(f"📊 Summary:")
        print(f"   • Total closed tickets: {all_data['metadata']['total_tickets']}")
        print(
            f"   • Date range: {all_data['metadata']['date_range']['start'][:10]} to {all_data['metadata']['date_range']['end'][:10]}"
        )

        # Display sample ticket structure
        if all_data["tickets"]:
            sample_ticket = all_data["tickets"][0]
            print(f"   • Sample ticket keys: {list(sample_ticket.keys())}")
            if "issue_details" in sample_ticket and sample_ticket["issue_details"]:
                detail_keys = (
                    list(sample_ticket["issue_details"].get("data", {}).keys())
                    if isinstance(sample_ticket["issue_details"], dict)
                    else []
                )
                print(f"   • Sample issue detail keys: {detail_keys}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    main()
