import unittest
from unittest.mock import Mock, patch

from agent import DEMO_CHAPTER_ID
from ui import EventMarketingApp


class LinkedInSharingTests(unittest.TestCase):
    def setUp(self):
        self.app = EventMarketingApp.__new__(EventMarketingApp)
        self.app.busy = False
        self.app.root = Mock()
        self.app.status = Mock()
        self.app.output_widgets = {"linkedin": Mock()}
        self.app.output_widgets["linkedin"].get.return_value = "Reviewed LinkedIn draft"
        self.event = {"chapter_id": "", "title": "Community event"}
        self.app._read_event = Mock(return_value=self.event)
        self.app.linkedin_draft_event = dict(self.event)

    @patch("ui.webbrowser.open", return_value=True)
    def test_copies_visible_draft_and_opens_linkedin(self, open_browser):
        self.app._share_linkedin_draft()

        self.app.root.clipboard_clear.assert_called_once_with()
        self.app.root.clipboard_append.assert_called_once_with(
            "Reviewed LinkedIn draft"
        )
        self.app.root.update.assert_called_once_with()
        open_browser.assert_called_once_with("https://www.linkedin.com/feed/")
        self.app.status.set.assert_called_once_with(
            "Draft copied. Paste it into LinkedIn, review it there, and click Post."
        )

    @patch("ui.webbrowser.open", return_value=False)
    def test_reports_draft_copied_when_browser_cannot_be_opened(self, open_browser):
        self.app._share_linkedin_draft()

        open_browser.assert_called_once_with("https://www.linkedin.com/feed/")
        self.app.status.set.assert_called_once_with(
            "Draft copied. Open LinkedIn in your browser, paste it, review it, and click Post."
        )

    @patch("ui.messagebox.showerror")
    @patch("ui.webbrowser.open", side_effect=OSError("browser unavailable"))
    def test_reports_browser_open_error_after_copy(self, _open_browser, showerror):
        self.app._share_linkedin_draft()

        self.app.root.clipboard_append.assert_called_once_with(
            "Reviewed LinkedIn draft"
        )
        showerror.assert_called_once_with(
            "Could not open LinkedIn",
            "The draft is copied, but LinkedIn could not be opened: browser unavailable",
        )

    @patch("ui.messagebox.showerror")
    @patch("ui.webbrowser.open")
    def test_blocks_demo_event(self, open_browser, showerror):
        self.event["chapter_id"] = DEMO_CHAPTER_ID
        self.app.linkedin_draft_event = dict(self.event)

        self.app._share_linkedin_draft()

        showerror.assert_called_once_with(
            "Demo content cannot be shared",
            "Switch to a live custom event or a real GDG event before sharing.",
        )
        self.app.root.clipboard_append.assert_not_called()
        open_browser.assert_not_called()

    @patch("ui.messagebox.showerror")
    @patch("ui.webbrowser.open")
    def test_blocks_draft_when_event_details_changed(self, open_browser, showerror):
        self.event["title"] = "Updated event title"

        self.app._share_linkedin_draft()

        showerror.assert_called_once_with(
            "Regenerate the draft",
            "Event details changed after this draft was generated. Generate a fresh draft before sharing.",
        )
        self.app.root.clipboard_append.assert_not_called()
        open_browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
