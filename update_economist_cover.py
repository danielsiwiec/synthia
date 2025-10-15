#!/usr/bin/env python3
"""
Update The Economist series cover in Kavita to use the most recent issue.
"""

import requests
import base64
import sys

KAVITA_URL = "http://localhost:45000"
API_KEY = "ac95056f-4a50-45a9-b77e-51e88650b0d4"

def main():
    print("🔐 Authenticating with Kavita...")

    # Step 1: Authenticate to get bearer token
    try:
        auth_response = requests.post(
            f"{KAVITA_URL}/api/Plugin/authenticate",
            params={"apiKey": API_KEY, "pluginName": "economist-cover-updater"}
        )
        auth_response.raise_for_status()
        token = auth_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✓ Authenticated successfully")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        sys.exit(1)

    # Step 2: Get all libraries to find the magazines library
    print("\n📚 Finding magazines library...")
    try:
        libraries_response = requests.get(
            f"{KAVITA_URL}/api/Library/libraries",
            headers=headers
        )
        libraries_response.raise_for_status()
        libraries = libraries_response.json()

        # Look for magazines library (type 2 is for books/magazines)
        magazine_lib = next(
            (lib for lib in libraries if lib.get("type") == 2),
            None
        )

        if not magazine_lib:
            print("✗ Could not find magazines library")
            sys.exit(1)

        library_id = magazine_lib["id"]
        print(f"✓ Found library: {magazine_lib['name']} (ID: {library_id})")
    except Exception as e:
        print(f"✗ Failed to get libraries: {e}")
        sys.exit(1)

    # Step 3: Find The Economist series
    print("\n🔍 Searching for The Economist series...")
    try:
        series_response = requests.post(
            f"{KAVITA_URL}/api/Series/v2",
            headers=headers,
            json={
                "statements": [],
                "combination": 1,
                "limitTo": 0,
                "pageNumber": 0,
                "pageSize": 500,
                "sortOptions": {"sortField": 1, "isAscending": False},
                "libraryId": library_id
            }
        )
        series_response.raise_for_status()
        all_series = series_response.json()

        # Find The Economist (exact match preferred)
        economist_matches = [s for s in all_series if "economist" in s["name"].lower()]

        if not economist_matches:
            print("✗ Could not find The Economist series")
            sys.exit(1)

        # Show all matches
        print(f"Found {len(economist_matches)} match(es):")
        for match in economist_matches:
            print(f"  - {match['name']} (ID: {match['id']})")

        # Prefer exact match "The Economist" or "The Economist USA"
        economist = next(
            (s for s in economist_matches if s["name"] in ["The Economist", "The Economist USA"]),
            economist_matches[0]  # fallback to first match
        )

        series_id = economist["id"]
        print(f"\n✓ Selected series: {economist['name']} (ID: {series_id})")
    except Exception as e:
        print(f"✗ Failed to find series: {e}")
        sys.exit(1)

    # Step 4: Get volumes and find most recent chapter
    print("\n📖 Finding most recent issue...")
    try:
        volumes_response = requests.get(
            f"{KAVITA_URL}/api/Series/volumes?seriesId={series_id}",
            headers=headers
        )
        volumes_response.raise_for_status()
        volumes = volumes_response.json()

        # Extract all chapters from all volumes
        all_chapters = []
        for volume in volumes:
            all_chapters.extend(volume.get("chapters", []))

        if not all_chapters:
            print("✗ No chapters found in series")
            sys.exit(1)

        # Find most recent by createdUtc timestamp
        most_recent_chapter = max(all_chapters, key=lambda c: c.get("createdUtc", ""))
        chapter_id = most_recent_chapter["id"]

        print(f"✓ Most recent issue: {most_recent_chapter.get('title', 'Unknown')} (Chapter ID: {chapter_id})")
        print(f"  Created: {most_recent_chapter.get('createdUtc', 'Unknown')}")
    except Exception as e:
        print(f"✗ Failed to get volumes: {e}")
        sys.exit(1)

    # Step 5: Get the chapter cover
    print("\n🖼️  Downloading chapter cover...")
    try:
        cover_response = requests.get(
            f"{KAVITA_URL}/api/Image/chapter-cover",
            params={"chapterId": chapter_id, "apiKey": API_KEY}
        )
        cover_response.raise_for_status()
        cover_data = cover_response.content

        if len(cover_data) < 1000:  # Sanity check
            print(f"✗ Cover data seems too small ({len(cover_data)} bytes)")
            sys.exit(1)

        print(f"✓ Downloaded cover ({len(cover_data)} bytes)")
    except Exception as e:
        print(f"✗ Failed to download cover: {e}")
        sys.exit(1)

    # Step 6: Upload as series cover
    print("\n⬆️  Updating series cover...")
    try:
        upload_response = requests.post(
            f"{KAVITA_URL}/api/Upload/series",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "id": series_id,
                "url": base64.b64encode(cover_data).decode('utf-8')
            }
        )
        upload_response.raise_for_status()

        print(f"✓ Successfully updated {economist['name']} cover!")
        print(f"  Series ID: {series_id}")
        print(f"  Chapter: {most_recent_chapter.get('title', 'Unknown')}")
        print("\n✅ Cover update complete!")
    except Exception as e:
        print(f"✗ Failed to upload cover: {e}")
        print(f"  Status code: {upload_response.status_code if 'upload_response' in locals() else 'N/A'}")
        sys.exit(1)

if __name__ == "__main__":
    main()
