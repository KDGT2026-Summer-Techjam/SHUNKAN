from django.test import TestCase


class HomeViewTests(TestCase):
    def test_home_page_is_available(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SHUNKAN")
