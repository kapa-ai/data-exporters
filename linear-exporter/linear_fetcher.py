import os
import requests
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

class LinearAPIClient:
    def __init__(self, api_key: str):
        """
        Initialize Linear API client

        Args:
            api_key: Your Linear API key (personal or OAuth token)
        """
        self.api_key = api_key
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    def _execute_query(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Linear API

        Args:
            query: GraphQL query string
            variables: Optional query variables

        Returns:
            Response data dict
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(self.base_url, headers=self.headers, json=payload)

        if response.status_code != 200:
            raise Exception(
                f"API request failed: {response.status_code} - {response.text}"
            )

        result = response.json()

        if "errors" in result:
            error_messages = "; ".join(e.get("message", "Unknown error") for e in result["errors"])
            raise Exception(f"GraphQL errors: {error_messages}")

        return result.get("data", {})

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the API connection and return organization info
        """
        query = """
        query {
            viewer {
                id
                name
                email
            }
            organization {
                id
                name
            }
        }
        """
        return self._execute_query(query)

    def fetch_closed_issues(
        self,
        days_back: int = 180,
        team_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all completed/cancelled issues from the last N days using cursor pagination.

        Args:
            days_back: Number of days to look back
            team_id: Optional team ID to filter by

        Returns:
            List of issue dicts
        """
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build filter based on FETCH_ALL_STATES mode.
        # Default (production): only completed/canceled issues.
        # With FETCH_ALL_STATES=true: all issues regardless of state (useful for testing).
        fetch_all = os.environ.get("FETCH_ALL_STATES", "").lower() in ("true", "1", "yes")

        if fetch_all:
            print("  (FETCH_ALL_STATES is ON — fetching issues in any state)")
            issue_filter: Dict[str, Any] = {
                "updatedAt": {"gte": cutoff_date},
            }
        else:
            issue_filter: Dict[str, Any] = {
                "updatedAt": {"gte": cutoff_date},
                "state": {
                    "type": {"in": ["completed", "canceled"]},
                },
            }
        if team_id:
            issue_filter["team"] = {"id": {"eq": team_id}}

        query = """
        query FetchClosedIssues($filter: IssueFilter!, $after: String) {
            issues(
                filter: $filter,
                first: 50,
                after: $after,
                orderBy: updatedAt
            ) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    identifier
                    number
                    title
                    description
                    descriptionState
                    url
                    priority
                    priorityLabel
                    createdAt
                    updatedAt
                    completedAt
                    canceledAt
                    state {
                        id
                        name
                        type
                    }
                    team {
                        id
                        name
                        key
                    }
                    assignee {
                        id
                        name
                        email
                    }
                    creator {
                        id
                        name
                        email
                    }
                    labels {
                        nodes {
                            id
                            name
                            color
                        }
                    }
                    project {
                        id
                        name
                    }
                    cycle {
                        id
                        name
                        number
                    }
                }
            }
        }
        """

        all_issues: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            variables: Dict[str, Any] = {"filter": issue_filter}
            if cursor:
                variables["after"] = cursor

            data = self._execute_query(query, variables)
            issues_data = data.get("issues", {})
            nodes = issues_data.get("nodes", [])

            if not nodes:
                break

            all_issues.extend(nodes)

            page_info = issues_data.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
                print(f"  Fetched {len(all_issues)} issues so far...")
            else:
                break

        return all_issues

    def fetch_issue_comments(self, issue_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all comments for a specific issue

        Args:
            issue_id: The Linear issue ID

        Returns:
            List of comment dicts
        """
        query = """
        query FetchComments($issueId: String!, $after: String) {
            issue(id: $issueId) {
                comments(first: 100, after: $after) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                        body
                        createdAt
                        updatedAt
                        user {
                            id
                            name
                            email
                        }
                        botActor {
                            name
                        }
                    }
                }
            }
        }
        """

        all_comments: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            variables: Dict[str, Any] = {"issueId": issue_id}
            if cursor:
                variables["after"] = cursor

            data = self._execute_query(query, variables)
            issue_data = data.get("issue", {})
            if not issue_data:
                break

            comments_data = issue_data.get("comments", {})
            nodes = comments_data.get("nodes", [])

            if not nodes:
                break

            all_comments.extend(nodes)

            page_info = comments_data.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        return all_comments

    def diagnose(self) -> None:
        """
        Print a summary of teams, workflow states, and recent issue counts
        so you can see what's actually in your Linear workspace.
        """
        # Teams
        data = self._execute_query("""
        query {
            teams {
                nodes { id name key issueCount }
            }
        }
        """)
        teams = data.get("teams", {}).get("nodes", [])
        print(f"\n{'='*50}")
        print("DIAGNOSTIC: Your Linear workspace")
        print(f"{'='*50}")
        print(f"\nTeams ({len(teams)}):")
        for t in teams:
            print(f"  - {t['name']} ({t['key']})  |  {t.get('issueCount', '?')} issues  |  ID: {t['id']}")

        # Workflow states
        data = self._execute_query("""
        query {
            workflowStates(first: 100) {
                nodes { id name type team { key } }
            }
        }
        """)
        states = data.get("workflowStates", {}).get("nodes", [])
        print(f"\nWorkflow states ({len(states)}):")
        for s in states:
            team_key = s.get("team", {}).get("key", "?")
            print(f"  - [{team_key}] {s['name']}  (type: {s['type']})")

        # Quick count: fetch 5 most recent issues regardless of state
        data = self._execute_query("""
        query {
            issues(first: 5, orderBy: updatedAt) {
                nodes {
                    identifier
                    title
                    state { name type }
                    updatedAt
                    completedAt
                }
            }
        }
        """)
        recent = data.get("issues", {}).get("nodes", [])
        print(f"\n5 most recently updated issues:")
        for iss in recent:
            state = iss.get("state", {})
            print(f"  - {iss['identifier']}: {iss['title'][:50]}")
            print(f"    state: {state.get('name')} (type: {state.get('type')})  |  updated: {iss['updatedAt'][:10]}  |  completedAt: {iss.get('completedAt', 'None')}")

        print(f"\n{'='*50}\n")

    def fetch_all_closed_tickets(self, days_back: int = 180, team_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch all closed/completed tickets with comments and full metadata.

        Args:
            days_back: Number of days to look back (default: 180)
            team_id: Optional team ID to restrict to

        Returns:
            Complete dataset of closed tickets with comments
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        print(
            f"Fetching completed issues from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

        # Fetch all completed issues
        print("Querying Linear for completed issues...")
        all_issues = self.fetch_closed_issues(days_back=days_back, team_id=team_id)
        print(f"Found {len(all_issues)} completed issues")

        # Fetch comments for each issue
        print(f"\nFetching comments for {len(all_issues)} issues...")
        all_tickets = []

        for i, issue in enumerate(all_issues, 1):
            issue_id = issue.get("id")
            identifier = issue.get("identifier", issue_id)

            if not issue_id:
                continue

            try:
                print(f"  Processing {i}/{len(all_issues)}: {identifier}")
                comments = self.fetch_issue_comments(issue_id)

                complete_ticket = {
                    "issue": issue,
                    "comments": comments,
                    "total_comments": len(comments),
                }

                all_tickets.append(complete_ticket)
                print(f"    Done ({len(comments)} comments)")

            except Exception as e:
                print(f"    Error: {str(e)}")
                # Still include the issue, just without comments
                all_tickets.append({
                    "issue": issue,
                    "comments": [],
                    "total_comments": 0,
                    "error": str(e),
                })

        result = {
            "metadata": {
                "total_tickets": len(all_tickets),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "days_back": days_back,
                "source": "linear",
            },
            "tickets": all_tickets,
        }

        print(
            f"\n✅ Successfully fetched {len(all_tickets)} completed tickets with comments"
        )
        return result


def main():
    """
    Main function — fetch completed Linear issues and save to JSON
    """
    import os

    API_KEY = os.environ.get("LINEAR_API_KEY", "")

    if not API_KEY:
        print("❌ Error: Set LINEAR_API_KEY environment variable")
        print("   Example: export LINEAR_API_KEY='lin_api_xxxxxxxxxxxx'")
        return

    # Optional: restrict to a specific team
    TEAM_ID = os.environ.get("LINEAR_TEAM_ID", None)

    client = LinearAPIClient(API_KEY)

    try:
        # Test connection
        print("Testing API connection...")
        viewer_data = client.test_connection()
        viewer = viewer_data.get("viewer", {})
        org = viewer_data.get("organization", {})
        print(f"✅ Connected as {viewer.get('name')} ({viewer.get('email')})")
        print(f"   Organization: {org.get('name')}")

        # Run diagnostic to show what's in your workspace
        client.diagnose()

        # Fetch all completed tickets (last 180 days)
        days_back = int(os.environ.get("LINEAR_DAYS_BACK", "180"))
        all_data = client.fetch_all_closed_tickets(days_back=days_back, team_id=TEAM_ID)

        # Save to JSON
        output_filename = (
            f"linear_closed_tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Data saved to: {output_filename}")
        print(f"📊 Summary:")
        print(f"   Total completed tickets: {all_data['metadata']['total_tickets']}")
        print(
            f"   Date range: {all_data['metadata']['date_range']['start'][:10]} to "
            f"{all_data['metadata']['date_range']['end'][:10]}"
        )

        if all_data["tickets"]:
            sample = all_data["tickets"][0]
            print(f"   Sample issue keys: {list(sample['issue'].keys())}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    main()
