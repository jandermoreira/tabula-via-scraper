"""
Fetch a Moodle quiz page after authenticating with a username and password.

This script logs in to a Moodle instance using the standard login form and then
downloads a fixed quiz page URL. The downloaded HTML is saved locally so it can
be inspected to determine where Moodle stores the quiz deadline or closing time.

This script does not parse grades, does not parse deadlines, and does not write
to Firestore. Its only purpose is to retrieve the authenticated quiz page HTML.
"""

import getpass
import html.parser
import http.cookiejar
import urllib.parse
import urllib.request


MOODLE_BASE_URL = "https://ava.ufscar.br"
LOGIN_URL = f"{MOODLE_BASE_URL}/login/index.php"
QUIZ_URL = "https://ava.ufscar.br/mod/quiz/view.php?id=1147861"

OUTPUT_FILE_PATH = "quiz.html"


class LoginTokenParser(html.parser.HTMLParser):
    """Extract the Moodle login token from the login page HTML."""

    def __init__(self):
        """Initialize the parser with an empty login token."""
        super().__init__()
        self.login_token = None

    def handle_starttag(self, tag_name, tag_attributes):
        """Inspect HTML start tags and capture the login token input value.

        Args:
            tag_name: The name of the HTML tag being processed.
            tag_attributes: The list of attributes attached to the HTML tag.
        """
        if tag_name != "input":
            return

        attribute_dictionary = dict(tag_attributes)

        if attribute_dictionary.get("name") == "logintoken":
            self.login_token = attribute_dictionary.get("value")


def create_authenticated_session_opener():
    """Create an HTTP opener that stores cookies between requests.

    Returns:
        A urllib opener configured with a cookie jar and a browser-like user agent.
    """
    session_cookie_jar = http.cookiejar.CookieJar()

    authenticated_session_opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(session_cookie_jar)
    )

    authenticated_session_opener.addheaders = [
        (
            "User-Agent",
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36",
        )
    ]

    return authenticated_session_opener


def fetch_login_token(authenticated_session_opener):
    """Fetch the Moodle login token from the login page.

    Args:
        authenticated_session_opener: The HTTP opener that stores session cookies.

    Returns:
        The login token string when present, otherwise None.
    """
    login_response = authenticated_session_opener.open(LOGIN_URL)
    login_page_html = login_response.read().decode("utf-8", errors="replace")

    login_token_parser = LoginTokenParser()
    login_token_parser.feed(login_page_html)

    return login_token_parser.login_token


def authenticate_with_moodle(authenticated_session_opener, moodle_username, moodle_password):
    """Authenticate with Moodle using the standard login form.

    Args:
        authenticated_session_opener: The HTTP opener that stores session cookies.
        moodle_username: The Moodle username.
        moodle_password: The Moodle password.

    Raises:
        RuntimeError: If Moodle returns a page that appears to indicate login failure.
    """
    login_token = fetch_login_token(authenticated_session_opener)

    login_form_fields = {
        "username": moodle_username,
        "password": moodle_password,
    }

    if login_token:
        login_form_fields["logintoken"] = login_token

    encoded_login_form_data = urllib.parse.urlencode(login_form_fields).encode("utf-8")

    login_request = urllib.request.Request(
        LOGIN_URL,
        data=encoded_login_form_data,
        method="POST",
    )

    login_response = authenticated_session_opener.open(login_request)
    login_response_html = login_response.read().decode("utf-8", errors="replace")

    if "loginerrormessage" in login_response_html:
        raise RuntimeError("Moodle login failed. Check the username and password.")


def fetch_quiz_page_html(authenticated_session_opener):
    """Download the fixed Moodle quiz page HTML.

    Args:
        authenticated_session_opener: The authenticated HTTP opener.

    Returns:
        The downloaded quiz page HTML as a string.
    """
    quiz_page_response = authenticated_session_opener.open(QUIZ_URL)
    quiz_page_html = quiz_page_response.read().decode("utf-8", errors="replace")

    return quiz_page_html


def save_text_file(output_file_path, text_content):
    """Save text content to a local file.

    Args:
        output_file_path: The path of the output file.
        text_content: The text content to write.
    """
    with open(output_file_path, "w", encoding="utf-8") as output_file:
        output_file.write(text_content)


def main():
    """Run the authentication flow and download the fixed quiz page."""
    print("Moodle quiz page fetcher")

    moodle_username = input("Username: ")
    moodle_password = getpass.getpass("Password: ")

    authenticated_session_opener = create_authenticated_session_opener()

    print("Authenticating with Moodle...")
    authenticate_with_moodle(
        authenticated_session_opener,
        moodle_username,
        moodle_password,
    )

    print("Fetching quiz page...")
    quiz_page_html = fetch_quiz_page_html(authenticated_session_opener)

    save_text_file(OUTPUT_FILE_PATH, quiz_page_html)

    print(f"Quiz page saved to: {OUTPUT_FILE_PATH}")


if __name__ == "__main__":
    main()