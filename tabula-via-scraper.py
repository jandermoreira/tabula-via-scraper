"""
This script provides functionality to log into a Moodle instance using credentials
from a YAML configuration file and user input for the password.
It also authenticates the user via Google OAuth 2.0 to access Cloud Firestore.
"""

import os
import sys
import getpass
from pprint import pprint

import requests
import yaml
import re
import uuid
from bs4 import BeautifulSoup
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.cloud import firestore


def load_moodle_config(config_file_path):
    """
    Loads Moodle configuration (base_url, username, and class_id) from a YAML file.

    Args:
        config_file_path (str): The path to the YAML configuration file.

    Returns:
        dict: A dictionary the config data

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If there's an error parsing the YAML file.
        ValueError: If 'base_url', 'username', or 'class_id' are missing in the Moodle section.
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        if (not config or
                'moodle' not in config or
                'base_url' not in config['moodle'] or
                'username' not in config['moodle']
        ):
            raise ValueError(
                f"Erro: Campos obrigatórios ausentes em {config_file_path}"
            )

        config_data = config['moodle']
        config_data['classes'] = config.get('classes', [])

        if 'get_password_from_file' in config_data and config_data['get_password_from_file']:
            try:
                with open('.moodle-password', 'r', encoding='utf-8') as password_file:
                    password = password_file.read().strip()
                    config_data['password'] = password
            except FileNotFoundError:
                print('Arquivo .moodle-password não encontrado. Ignorado.')

        return config_data

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Erro: O arquivo de configuração '{config_file_path}' não foi encontrado.")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Erro ao processar o arquivo YAML '{config_file_path}': {e}")


def load_firebase_config(config_file_path):
    """
    Loads Firebase configuration (active environment, project_id, client_secrets_file) from a YAML file.

    Args:
        config_file_path (str): The path to the YAML configuration file.

    Returns:
        dict: A dictionary containing Firebase configuration parameters.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If there's an error parsing the YAML file.
        ValueError: If mandatory configuration fields are missing.
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        firebase_config = config.get('firebase', {})
        active_env = firebase_config.get('active_env', 'dev')
        environments = firebase_config.get('environments', {})

        if environments and active_env in environments:
            env_data = environments[active_env]
            project_id = env_data.get('project_id')
            client_secrets_file = env_data.get('client_secrets_file')
        else:
            project_id = firebase_config.get('project_id')
            client_secrets_file = firebase_config.get('client_secrets_file')

        if not project_id or not client_secrets_file:
            raise ValueError(
                f"Erro: 'project_id' ou 'client_secrets_file' ausentes para o ambiente ativo '{active_env}' em {config_file_path}"
            )

        return {
            'active_env': active_env,
            'project_id': project_id,
            'client_secrets_file': client_secrets_file
        }

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Erro: O arquivo de configuração '{config_file_path}' não foi encontrado.")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Erro ao processar o arquivo YAML '{config_file_path}': {e}")


def authenticate_google_user(client_secrets_file, token_file=".user_token.json"):
    """
    Authenticates the user using Google OAuth 2.0 browser flow or cached credentials, returning the user's ID token and credentials.

    Args:
        client_secrets_file (str): Path to Google OAuth client secrets JSON file.
        token_file (str, optional): Path to store or read cached user credentials.

    Returns:
        tuple: (user_email, user_id, credentials) of the authenticated user.
    """
    from google.oauth2.credentials import Credentials

    if not os.path.exists(client_secrets_file):
        raise FileNotFoundError(
            f"Arquivo de cliente OAuth ('{client_secrets_file}') não foi encontrado na pasta."
        )

    scopes = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/datastore'
    ]

    creds = None
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, scopes)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes=scopes)
            creds = flow.run_local_server(port=0)

        try:
            with open(token_file, 'w', encoding='utf-8') as token_out:
                token_out.write(creds.to_json())
        except Exception as err:
            print(f"Aviso: Não foi possível salvar o token de sessão local: {err}")

    user_email = None
    user_id = None
    if creds.id_token:
        try:
            token_info = id_token.verify_oauth2_token(creds.id_token, Request())
            user_email = token_info.get('email')
            user_id = token_info.get('sub')
        except Exception:
            pass

    if not user_email or not user_id:
        try:
            resp = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {creds.token}'}
            )
            if resp.status_code == 200:
                data = resp.json()
                user_email = data.get('email')
                user_id = data.get('sub')
        except Exception as e:
            print(f"Erro ao obter dados do perfil do usuário: {e}")

    return user_email, user_id, creds


def init_firebase_user_client(user_credentials, project_id):
    """
    Initializes a Firestore client using user OAuth credentials for multi-tenant isolation.

    Args:
        user_credentials (google.auth.credentials.Credentials): The authenticated user credentials.
        project_id (str): Firebase project ID.

    Returns:
        google.cloud.firestore.Client: Firestore client instance acting on behalf of the user.
    """
    return firestore.Client(project=project_id, credentials=user_credentials)


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
        response.raise_for_status()

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
        }

        post_response = session.post(login_page_url, data=login_payload)
        post_response.raise_for_status()

        if "loginerror" in post_response.url or "login/index.php" in post_response.url:
            return None

        return session

    except requests.exceptions.RequestException as e:
        print(f"Erro de requisição durante o login: {e}")
        return None
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        return None


def get_hidden_password(prompt="Digite sua senha do Moodle: "):
    """
    Prompts for a password without echoing characters to the terminal, avoiding GetPassWarning.

    Args:
        prompt (str): The prompt message to display.

    Returns:
        str: The entered password.
    """
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        try:
            import termios
            import tty

            with open('/dev/tty', 'r+') as tty_file:
                fd = tty_file.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty_file.write(prompt)
                    tty_file.flush()
                    tty.setcbreak(fd)
                    password = ""
                    while True:
                        ch = tty_file.read(1)
                        if ch in ('\r', '\n'):
                            tty_file.write('\n')
                            tty_file.flush()
                            break
                        elif ch in ('\x03', '\x04'):
                            tty_file.write('\n')
                            tty_file.flush()
                            raise KeyboardInterrupt
                        elif ch in ('\x7f', '\x08'):
                            if password:
                                password = password[:-1]
                        else:
                            password += ch
                    return password
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

        return getpass.getpass(prompt)


def extract_course_info(soup):
    """
    Extracts course name, year, and term from the Moodle page HTML.

    Args:
        soup (BeautifulSoup): Parsed HTML page.

    Returns:
        dict: A dictionary containing 'course_name', 'year', and 'term'.
    """
    course_name = "Desconhecida"
    year = "N/A"
    term = "N/A"

    # Extract Course Name (Page Header or Breadcrumbs)
    header_node = soup.find('header', id='page-header')
    if header_node:
        h1 = header_node.find('h1')
        if h1:
            course_name = h1.get_text(strip=True)

    if course_name == "Desconhecida":
        breadcrumb = soup.find('nav', attrs={
            'aria-label': re.compile(r'Navegação|Navigation', re.I)}) or soup.find('ul',
                                                                                   class_='breadcrumb')
        if breadcrumb:
            links = breadcrumb.find_all('a')
            if links:
                course_name = links[-1].get_text(strip=True)

    # Extract Shortname / Course Code (e.g., GRAD_1001350_A_SAO_CARLOS_2026_1)
    full_text = soup.get_text()
    match = re.search(r'GRAD_[A-Za-z0-9_]+_(\d{4})_(\d+)', full_text)

    if not match:
        # Search inside attribute values or script tags if not found in plain text
        match = re.search(r'(\d{4})_(\d+)', full_text)

    if match:
        year = match.group(1)
        term = match.group(2)

    return {
        'course_name': course_name,
        'year': year,
        'term': term
    }


def create_class_in_firestore(db_client, user_email, class_info):
    """
    Creates a class document in Firestore with the extracted course information.

    Args:
        db_client (google.cloud.firestore.Client): Firestore client instance.
        user_email (str): The authenticated user's email.
        class_info (dict): Dictionary containing 'course_name', 'year', and 'term'.

    Returns:
        str: The class ID (UUID) of the created document.
    """
    class_id = class_info['classId']

    class_doc = {
        'classId': class_id,
        'className': class_info['course_name'],
        'academicYear': class_info['year'],
        'period': class_info['term'],
        'numberOfClasses': 0
    }

    class_ref = db_client.collection('users').document(user_email).collection('classes').document(
        class_id)
    class_ref.set(class_doc)

    print(f"Turma criada no Firebase: {class_id}")
    print(f"  Nome: {class_info['course_name']}")
    print(f"  Ano: {class_info['year']}")
    print(f"  Período: {class_info['term']}")

    return class_id


def fetch_class_information(url, class_id):
    """
    Fetches course information from Moodle.

    Args:
        url (str): The base URL of the Moodle instance.
        class_id (str): The course ID in Moodle.

    Returns:
        dict: A dictionary with course information.
    """
    course_page_url = f"{url}/user/index.php?id={class_id}"
    print(f"Obtendo dados da disciplina de: {course_page_url}")
    response = authenticated_session.get(course_page_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    class_info = extract_course_info(soup)
    class_info['classId'] = class_id

    return class_info


if __name__ == "__main__":
    config_file_path = "scraper_config.yaml"

    try:
        # Load Firebase configuration
        firebase_config_data = load_firebase_config(config_file_path)
        FIREBASE_ACTIVE_ENV = firebase_config_data['active_env']
        FIREBASE_PROJECT_ID = firebase_config_data['project_id']
        FIREBASE_CLIENT_SECRETS_FILE = firebase_config_data['client_secrets_file']

        # Authenticate user via Google OAuth
        print('Fazendo login no Google... ')
        token_file = ".user_token.json"
        user_email, user_id, user_creds = authenticate_google_user(FIREBASE_CLIENT_SECRETS_FILE,
                                                                   token_file)
        print(f"Usuário autenticado: {user_email}")
        print(f'AVISO: *** Sessão salva em {token_file}. Não compartilhe este arquivo!')

        # Initialize Firestore client using user OAuth credentials
        db_client = init_firebase_user_client(user_creds, FIREBASE_PROJECT_ID)
        print("Conexão com o Firebase Firestore iniciada")

        if (FIREBASE_ACTIVE_ENV == 'dev'):
            print('\nAVISO: *** Ambiente de desenvolvimento ***')
            print(f"       Ambiente ativo: {FIREBASE_ACTIVE_ENV} " +
                  f"(Projeto ID: {FIREBASE_PROJECT_ID})\n")

        # Load  Moodle configuration
        moodle_config_data = load_moodle_config(config_file_path)
        MOODLE_BASE_URL = moodle_config_data['base_url']
        MOODLE_USERNAME = str(moodle_config_data['username'])
        sys.stdout.flush()
        if 'password' in moodle_config_data:
            MOODLE_PASSWORD = moodle_config_data['password']
        else:
            MOODLE_PASSWORD = getpass.getpass(("Digite sua senha do Moodle: "))

        print(f"Fazendo login no Moodle...", end='')
        authenticated_session = login_moodle(MOODLE_USERNAME, MOODLE_PASSWORD, MOODLE_BASE_URL)
        if not authenticated_session:
            print(" Falhou. Confira sua senha.")
        else:
            print(" Ok.")

            for class_data in moodle_config_data['classes']:
                class_id = str(class_data["class_id"])
                print(f'Buscando dados da turma {class_id}...')
                class_info = fetch_class_information(MOODLE_BASE_URL, class_id)

                # Create class in Firestore
                create_class_in_firestore(db_client, user_email, class_info)

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        print(f"Erro de configuração: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        sys.exit(1)
