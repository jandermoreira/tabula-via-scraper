"""
This script provides functionality to log into a Moodle instance using credentials
from a YAML configuration file and user input for the password.
It utilizes the requests library for HTTP communication and BeautifulSoup for HTML parsing.
"""

import requests
from bs4 import BeautifulSoup
import yaml
import getpass


def load_moodle_config(config_file_path):
    """
    Loads Moodle configuration (base_url and username) from a YAML file.

    Args:
        config_file_path (str): The path to the YAML configuration file.

    Returns:
        dict: A dictionary containing 'base_url' and 'username' for Moodle.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If there's an error parsing the YAML file.
        ValueError: If 'base_url' or 'username' are missing in the Moodle section.
    """
    try:
        with open(config_file_path, 'r') as file:
            config = yaml.safe_load(file)

        moodle_config = config.get('moodle', {})
        base_url = moodle_config.get('base_url')
        username = moodle_config.get('username')

        if not base_url or not username:
            raise ValueError(
                f"Error: 'base_url' or 'username' not found in the 'moodle' section of {config_file_path}"
            )

        return {'base_url': base_url, 'username': username}

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: The configuration file '{config_file_path}' was not found.")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error parsing the YAML file '{config_file_path}': {e}")


def login_moodle(username, password, moodle_url):
    """
    Performs login to a Moodle instance.

    Args:
        username (str): The username for login.
        password (str): The password for login.
        moodle_url (str): The base URL of the Moodle instance (e.g., "https://moodle.example.com").

    Returns:
        requests.Session: An authenticated session if login is successful, None otherwise.
    """
    session = requests.Session()
    login_page_url = f"{moodle_url}/login/index.php"

    try:
        response = session.get(login_page_url)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        soup = BeautifulSoup(response.text, 'html.parser')

        logintoken_input = soup.find('input', {'name': 'logintoken'})
        logintoken = logintoken_input['value'] if logintoken_input else None

        if not logintoken:
            print("Erro: Não foi possível encontrar o token de login na página.")
            return None

        login_payload = {
            'username': username,
            'password': password,
            'logintoken': logintoken,
            # Other fields that might be necessary, depending on the Moodle version
            # 'anchor': '',
            # 'rememberusername': 1,
        }

        post_response = session.post(login_page_url, data=login_payload)
        post_response.raise_for_status()

        if "loginerror" in post_response.url or "login/index.php" in post_response.url:
            print("Login falhou: Verifique suas credenciais.")
            return None

        print(f"Login bem-sucedido para o usuário: {username}")
        return session

    except requests.exceptions.RequestException as e:
        print(f"Erro de requisição durante o login: {e}")
        return None
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        return None


if __name__ == "__main__":
    config_file_path = "scraper_config.yaml"

    try:
        moodle_config_data = load_moodle_config(config_file_path)
        MOODLE_BASE_URL = moodle_config_data['base_url']
        MOODLE_USERNAME = moodle_config_data['username']

        MOODLE_PASSWORD = getpass.getpass("Digite sua senha do Moodle: ")

        print(f"Tentando fazer login no Moodle em {MOODLE_BASE_URL} " +
              f"com o usuário {MOODLE_USERNAME}...")
        authenticated_session = login_moodle(str(MOODLE_USERNAME), MOODLE_PASSWORD, MOODLE_BASE_URL)

        if authenticated_session:
            print("Sessão autenticada criada. Você pode usá-la para outras requisições.")
            # Example: Access the Moodle home page with the authenticated session
            # home_page_response = authenticated_session.get(MOODLE_BASE_URL)
            # print(home_page_response.text[:500]) # Prints the first 500 characters of the home page
        else:
            print("Não foi possível autenticar no Moodle.")

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        print(f"Erro de configuração: {e}")
        exit(1)
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        exit(1)
