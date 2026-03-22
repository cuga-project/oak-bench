"""
Tests for Medical Information endpoint:
- POST /get_medical_information
"""

import pytest


class TestGetMedicalInformation:
    """Tests for POST /get_medical_information endpoint."""

    def test_known_topic_high_blood_pressure(self, client, basic_request_body):
        """Test Case 1: Known topic returns seeded articles."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "high blood pressure", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "status" in data
        assert "items" in data

        assert data["status"] == "OK"
        assert len(data["items"]) <= 5

        # Check article structure
        for article in data["items"]:
            assert "id" in article
            assert "type" in article
            assert "title" in article
            assert "abstract" in article
            assert "url" in article

            # Check multilingual content
            assert "consumer" in article["title"]
            assert "en-us" in article["title"]["consumer"]
            assert "en-ca" in article["title"]["consumer"]
            assert "es-us" in article["title"]["consumer"]

            assert "consumer" in article["abstract"]

            # Verify content is about hypertension
            title_en = article["title"]["consumer"]["en-us"].lower()
            assert "blood pressure" in title_en or "hypertension" in title_en

    def test_pagination_for_large_result_set(self, client, basic_request_body):
        """Test Case 2: Pagination works for topics with many articles."""
        # Get first page
        response1 = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "high blood pressure", "page_index": 0, "size": 5},
        )

        # Get second page
        response2 = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "high blood pressure", "page_index": 1, "size": 5},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        page1_data = response1.json()
        page2_data = response2.json()

        # Both should be OK
        assert page1_data["status"] == "OK"
        assert page2_data["status"] == "OK"

        # No duplicates between pages
        page1_ids = {article["id"] for article in page1_data["items"]}
        page2_ids = {article["id"] for article in page2_data["items"]}

        assert len(page1_ids & page2_ids) == 0, (
            "Pages should not have duplicate articles"
        )

    def test_unknown_topic_synthesized_results(self, client, basic_request_body):
        """Test Case 3: Unknown topic returns synthesized articles."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "rare disease xyz", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "OK"
        assert len(data["items"]) == 5  # Should synthesize 6 articles, return 5

        # Check synthesized article structure
        article = data["items"][0]
        assert "id" in article
        assert article["id"].startswith("gen-")

        # Title should include the query topic
        title_en = article["title"]["consumer"]["en-us"]
        assert "Rare Disease Xyz" in title_en or "rare disease xyz" in title_en.lower()

        # URL should point to search endpoint
        assert "search" in article["url"]
        assert "rare disease xyz" in article["url"].lower()

    def test_empty_page(self, client, basic_request_body):
        """Test Case 4: Out of range page returns appropriate status."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "diabetes", "page_index": 10, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return empty items with appropriate status
        assert len(data["items"]) == 0
        assert data["status"] in ["PAGE_OUT_OF_RANGE", "NO_RESULTS"]

    def test_diabetes_topic(self, client, basic_request_body):
        """Test Case 5: Diabetes topic returns seeded articles."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "diabetes", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "OK"
        assert len(data["items"]) > 0

        # Verify content is about diabetes
        for article in data["items"]:
            title_en = article["title"]["consumer"]["en-us"].lower()
            abstract_en = article["abstract"]["consumer"]["en-us"].lower()
            assert "diabetes" in title_en or "diabetes" in abstract_en

    def test_knee_surgery_topic(self, client, basic_request_body):
        """Test Case 6: Knee surgery topic returns seeded articles."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "knee surgery", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "OK"
        assert len(data["items"]) == 4  # Knee surgery has 4 articles

        # Verify content is about knee surgery
        for article in data["items"]:
            title_en = article["title"]["consumer"]["en-us"].lower()
            assert "knee" in title_en

    def test_custom_page_size(self, client, basic_request_body):
        """Test Case 7: Custom page size is respected."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "high blood pressure", "page_index": 0, "size": 3},
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) <= 3

    def test_fuzzy_matching(self, client, basic_request_body):
        """Test Case 8: Fuzzy matching works for partial queries."""
        # Search for "pressure" should match "high blood pressure"
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "pressure", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        # Should find articles (either seeded or synthesized)
        assert len(data["items"]) > 0

    def test_case_insensitive_search(self, client, basic_request_body):
        """Test Case 9: Search is case-insensitive."""
        # Search with different cases
        response1 = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "DIABETES", "page_index": 0, "size": 5},
        )

        response2 = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "diabetes", "page_index": 0, "size": 5},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Should return same results
        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["items"]) == len(data2["items"])

    def test_multilingual_content_structure(self, client, basic_request_body):
        """Test Case 10: All articles have complete multilingual content."""
        response = client.post(
            "/get_medical_information",
            json=basic_request_body,
            params={"query": "high blood pressure", "page_index": 0, "size": 5},
        )

        assert response.status_code == 200
        data = response.json()

        for article in data["items"]:
            # Title should have all three locales
            title = article["title"]["consumer"]
            assert "en-us" in title
            assert "en-ca" in title
            assert "es-us" in title
            assert len(title["en-us"]) > 0
            assert len(title["en-ca"]) > 0
            assert len(title["es-us"]) > 0

            # Abstract should have all three locales
            abstract = article["abstract"]["consumer"]
            assert "en-us" in abstract
            assert "en-ca" in abstract
            assert "es-us" in abstract
            assert len(abstract["en-us"]) > 0
            assert len(abstract["en-ca"]) > 0
            assert len(abstract["es-us"]) > 0
