import getpass
import html.parser
import http.cookiejar
import urllib.parse
import urllib.request


MOODLE_BASE_URL = "https://ava.ufscar.br/"
LOGIN_URL = f"{MOODLE_BASE_URL}/login/index.php"
GRADEBOOK_URL = f"{MOODLE_BASE_URL}/grade/report/grader/index.php?id=36723"

OUTPUT_FILE = "gradebook.html"


class LoginTokenParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.logintoken = None

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return

        attributes = dict(attrs)

        if attributes.get("name") == "logintoken":
            self.logintoken = attributes.get("value")


def create_opener():
    cookie_jar = http.cookiejar.CookieJar()

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )

    opener.addheaders = [
        (
            "User-Agent",
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36",
        )
    ]

    return opener


def fetch_login_token(opener):
    response = opener.open(LOGIN_URL)
    html = response.read().decode("utf-8", errors="replace")

    parser = LoginTokenParser()
    parser.feed(html)

    return parser.logintoken


def login(opener, username, password):
    logintoken = fetch_login_token(opener)

    form_data = {
        "username": username,
        "password": password,
    }

    if logintoken:
        form_data["logintoken"] = logintoken

    encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")

    request = urllib.request.Request(
        LOGIN_URL,
        data=encoded_data,
        method="POST",
    )

    response = opener.open(request)
    html = response.read().decode("utf-8", errors="replace")

    if "loginerrormessage" in html or "Nome de usuário ou senha errados" in html:
        raise RuntimeError("Falha no login. Verifique usuário e senha.")

    return html


def fetch_gradebook(opener):
    response = opener.open(GRADEBOOK_URL)
    html = response.read().decode("utf-8", errors="replace")

    return html


def save_html(html):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(html)


def main():
    print("Login no Moodle")
    username = input("Usuário: ")
    password = getpass.getpass("Senha: ")

    opener = create_opener()

    print("Autenticando...")
    login(opener, username, password)

    print("Obtendo livro de notas...")
    gradebook_html = fetch_gradebook(opener)

    save_html(gradebook_html)

    print(f"Página salva em: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()