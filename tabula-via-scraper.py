"""
This script provides functionality to log into a Moodle instance using credentials
from a YAML configuration file and user input for the password.
It also authenticates the user via Google OAuth 2.0 to access Cloud Firestore.
"""
import datetime
import os
import sys
import getpass
from pprint import pprint

import requests
import yaml
import re
from bs4 import BeautifulSoup
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.cloud import firestore


# Terminal output with colors
class Output:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    def warning(self, text, **kwargs):
        """
        Prints a warning message.
        :param text: Text to be printed
        :param kwargs: any additional keyword arguments to be passed to print()
        """
        print(f"{Output.YELLOW}Aviso{Output.RESET}: {text}", **kwargs)

    def error(self, text, **kwargs):
        """
        Prints an error message.
        :param text: Text to be printed
        :param kwargs: any additional keyword arguments to be passed to print()
        """
        print(f"{Output.RED}Erro{Output.RESET}: {text}", **kwargs)

    def highlight(self, text):
        """
        Returns a highlighted text (in blue).
        :param text: Text to be highlighted
        :return: Text with highlighting
        """
        return f"{Output.BLUE}{text}{Output.RESET}"


output = Output()


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
                f"{Output.RED}Erro{Output.RESET}: Campos obrigatórios ausentes em {config_file_path}"
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
            f"{Output.RED}Erro{Output.RESET}: O arquivo de configuração '{config_file_path}' não foi encontrado.")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(
            f"{Output.RED}Erro{Output.RESET}: processando arquivo YAML '{config_file_path}': {e}")


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
                f"{Output.RED}Erro{Output.RESET}: 'project_id' ou 'client_secrets_file' ausentes para o ambiente ativo '{active_env}' em {config_file_path}"
            )

        return {
            'active_env': active_env,
            'project_id': project_id,
            'client_secrets_file': client_secrets_file
        }

    except FileNotFoundError:
        raise FileNotFoundError("Arquivo de configuração "
                                f"{output.highlight(config_file_path)} não encontrado")
    except yaml.YAMLError as e:
        raise yaml.YAMLError("Falha ao processar o arquivo YAML "
                             f"{output.highlight(config_file_path)} ({e})")


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
        raise FileNotFoundError(f"Arquivo de cliente "
                                f"({output.highlight(client_secrets_file)}) não foi encontrado")

    scopes = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/datastore'
    ]

    credentials = None
    if os.path.exists(token_file):
        try:
            credentials = Credentials.from_authorized_user_file(token_file, scopes)
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception:
                credentials = None

        if not credentials:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes=scopes)
            credentials = flow.run_local_server(port=0)

        try:
            with open(token_file, 'w', encoding='utf-8') as token_out:
                token_out.write(credentials.to_json())
        except Exception as e:
            output.warning(f"Não foi possível salvar o token de sessão local ({e})")

    user_email = None
    user_id = None
    if credentials.id_token:
        try:
            token_info = id_token.verify_oauth2_token(credentials.id_token, Request())
            user_email = token_info.get('email')
            user_id = token_info.get('sub')
        except Exception:
            pass

    if not user_email or not user_id:
        try:
            resp = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {credentials.token}'}
            )
            if resp.status_code == 200:
                data = resp.json()
                user_email = data.get('email')
                user_id = data.get('sub')
        except Exception as e:
            output.error(f"Falha ao obter dados do perfil do usuário ({e})")

    return user_email, user_id, credentials


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
            print(
                "{Colors.RED}Erro{Colors.RESET}: Não foi possível encontrar o token de login na página.",
                end='')
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
        output.error(f"Requisição de login falhou ({e})", end='')
        return None
    except Exception as e:
        output.error(f"Falha inesperada durante o login: {e}", end='')
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

    if course_name == "Desconhecida" or year == "N/A" or term == "N/A":
        return None

    return {
        'course_name': course_name,
        'year': year,
        'term': term
    }


def fetch_student_list_data(session, moodle_base_url, class_id):
    """
    Fetches the list of students for a given class ID,
    filtering by role 'Estudante'.

    Args:
        session (requests.Session): An authenticated requests session.
        moodle_base_url (str): The base URL of the Moodle instance.
        class_id (str): The ID of the class to fetch the student list from.

    Returns:
        list: A list of dictionaries, each representing a student with 'id_number' and 'name'.
    """
    initial_student_list_url = f"{moodle_base_url}/user/index.php?id={class_id}"
    filtered_students = []

    try:
        full_list_url = f"{initial_student_list_url}&perpage=-1"

        response = session.get(full_list_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        user_table = soup.find('table', id='participants')
        if not user_table:
            return []

        headers = [th.get_text(strip=True) for th in user_table.find('thead').find_all('th')]

        name_idx = -1
        id_number_idx = -1
        roles_idx = -1
        status_idx = -1

        for i, header in enumerate(headers):
            header_lower = header.lower()
            if "nome" in header_lower or "sobrenome" in header_lower:
                name_idx = i
            elif "número de identificação" in header_lower or "número de id" in header_lower or "id number" in header_lower:
                id_number_idx = i
            elif "papéis" in header_lower or "roles" in header_lower:
                roles_idx = i
            elif "situação" in header_lower or "status" in header_lower:
                status_idx = i

        if name_idx == -1 or id_number_idx == -1 or roles_idx == -1 or status_idx == -1:
            return []

        rows = user_table.find('tbody').find_all('tr')
        for row in rows:
            all_cells = row.find_all(['th', 'td'])

            if len(all_cells) > max(name_idx, id_number_idx, roles_idx, status_idx):
                name_cell = all_cells[name_idx]
                name_tag = name_cell.find('a', class_='aabtn')
                full_name = name_tag.get_text(strip=True) if name_tag else ""

                id_number = all_cells[id_number_idx].get_text(strip=True)
                roles = all_cells[roles_idx].get_text(strip=True)

                status_cell = all_cells[status_idx]
                status_div = status_cell.find('div', attrs={'data-status': True})
                if status_div:
                    moodle_status = status_div['data-status']
                else:
                    moodle_status = status_cell.get_text(strip=True)

                # Map Moodle status to Firestore status
                if roles.strip().lower() == "estudante":
                    if full_name:
                        firestore_status = "ACTIVE" if moodle_status.strip().lower() == "ativo" else "CANCELED"
                        if not id_number:
                            print(
                                f"{Output.YELLOW}Aviso{Output.RESET}: {full_name} ignorado. Número de identificação ausente.")
                        else:
                            filtered_students.append({
                                'classId': class_id,
                                'displayName': "",
                                'name': full_name,
                                'status': firestore_status,
                                'studentId': id_number,
                                'studentNumber': id_number
                            })

    except requests.exceptions.RequestException as e:
        return []
    except Exception as e:
        return []

    # Sort students by name
    sorted_students = sorted(filtered_students, key=lambda student: student['name'])
    return sorted_students


def create_class_in_firestore(db_client, user_email, class_info):
    """
    Creates a class document in Firestore with the extracted course information.
    Then, creates student documents in a 'students' subcollection.

    Args:
        db_client (google.cloud.firestore.Client): Firestore client instance.
        user_email (str): The authenticated user's email.
        class_info (dict): Dictionary containing 'course_name', 'year', 'term', 'numberOfSessions', and 'studentList'.

    Returns:
        str: The class ID (UUID) of the created document.
    """
    class_id = class_info['classId']
    student_list = class_info.get('studentList', [])

    class_doc = {
        'classId': class_id,
        'className': class_info['course_name'],
        'academicYear': class_info['year'],
        'period': class_info['term'],
        'numberOfSessions': class_info['numberOfSessions'],
    }

    class_ref = db_client.collection('users').document(user_email).collection('classes').document(
        class_id)
    class_ref.set(class_doc)

    # Create student documents in a subcollection
    if student_list:
        students_collection_ref = class_ref.collection('students')
        for student_data in student_list:
            student_id = student_data['studentId']
            students_collection_ref.document(student_id).set(student_data)

    return class_id


def fetch_class_information(url, class_data):
    """
    Fetches course information from Moodle.

    Args:
        url (str): The base URL of the Moodle instance.
        class_id (str): The course ID in Moodle.

    Returns:
        dict: A dictionary with course information and student list.
    """
    class_id = class_data['class_id']

    course_page_url = f"{url}/user/index.php?id={class_id}"
    response = authenticated_session.get(course_page_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    class_info = extract_course_info(soup)
    if class_info:
        class_info['classId'] = class_id
    else:
        return None

    # Fetch student list
    student_list = fetch_student_list_data(authenticated_session, url, class_id)
    class_info['studentList'] = student_list

    if "title" in class_data:
        class_info['course_name'] = class_data["title"]
    if "number_of_sessions" in class_data:
        class_info['numberOfSessions'] = class_data["number_of_sessions"]
    else:
        class_info['numberOfSessions'] = 15
        output.warning(f"Número de aulas indefinido."
                       f"Assumindo {output.highlight(class_info['numberOfSessions'])} aulas.")

    return class_info


def fetch_single_evidence(url, evidence_data):
    """
    Parses and fetches evidence details for a single assessment item.

    :param url: Moodle base URL
    :param evidence_data: Config info of an evidence item
    :return: dict with processed evidence information or empty dict if invalid
    """
    evidence_information = {'title': evidence_data['title']}

    if 'gradebook_name' not in evidence_data and 'quiz_id' not in evidence_data:
        output.error(f"Dados insuficientes para '{evidence_information['title']}' - "
                     f"{output.highlight('gradebook_name')} ou {output.highlight('quiz_id')} necessárias")
        output.warning(f"Entrada '{evidence_information['title']}' ignorada.")
        return {}

    if 'gradebook_name' in evidence_data:
        if 'deadline' not in evidence_data and 'deadline_quiz_id' not in evidence_data:
            output.error(f"Em '{evidence_information['title']}' - "
                         f"Não há {output.highlight('deadline')} nem {output.highlight('deadline_quiz_id')}.")
            output.warning(f"Entrada '{evidence_information['title']}' ignorada.")
            return {}
        evidence_information['scores'] = [  # Placeholder for get scores from gradebook
            {'student_id': 887766, 'score': 6.0},
            {'student_id': 887700, 'score': 6.0}
        ]

    if 'deadline' in evidence_data:
        deadline = evidence_data['deadline']
        if not isinstance(deadline, datetime.date):
            output.error(f"{output.highlight('deadline')} não é uma data válida (AAAA-MM-DD).")
            output.warning(f"Entrada '{evidence_information['title']}' ignorada.")
            return {}
        evidence_information['deadline'] = deadline

    if 'deadline_quiz_id' in evidence_data:
        if 'deadline' in evidence_information:
            output.warning(f"Em '{evidence_information['title']}' - "
                           f"{output.highlight('deadline_quiz_id')} ignorada "
                           f"({output.highlight('deadline')} especificada)")
        evidence_information['deadline'] = datetime.date(2027, 12,
                                                         25)  # Placeholder for getting deadline from Moodle

    if 'quiz_id' in evidence_data:
        if 'scores' in evidence_information:
            output.warning(f"Em '{evidence_information['title']}' - "
                           f"{output.highlight('quiz_id')} ignorada "
                           f"({output.highlight('gradebook_name')} especificada)")
        else:
            evidence_information['scores'] = [  # Placeholder for get scores from gradebook
                {'student_id': 887766, 'score': 5.0},
                {'student_id': 887700, 'score': 5.0}
            ]

    return evidence_information


def fetch_class_evidences(url, class_data):
    """
    Fetches all evidence items for a given class configuration.

    Args:
        url (str): The base URL of the Moodle instance.
        class_data (dict): Class configuration dictionary.

    Returns:
        list: A list of dictionaries representing processed evidences.
    """
    if "evidences" not in class_data:
        return []

    evidences_data = class_data['evidences']
    evidences_list = []

    categories = [
        ('consolidation', 'CONSOLIDATION'),
        ('monitoring', 'MONITORING')
    ]

    for category_key, category_type in categories:
        if category_key in evidences_data:
            for item in evidences_data[category_key]:
                evidence_info = fetch_single_evidence(url, item)
                if evidence_info:
                    evidence_info['type'] = category_type
                    evidences_list.append(evidence_info)

    print("Info:")
    pprint(evidences_list)

    return evidences_list


if __name__ == "__main__":
    config_file_path = "scraper_config.yaml"

    try:
        # Load Firebase configuration
        firebase_config_data = load_firebase_config(config_file_path)
        FIREBASE_ACTIVE_ENV = firebase_config_data['active_env']
        FIREBASE_PROJECT_ID = firebase_config_data['project_id']
        FIREBASE_CLIENT_SECRETS_FILE = firebase_config_data['client_secrets_file']

        if (FIREBASE_ACTIVE_ENV == 'dev'):
            output.warning(output.highlight("Usando ambiente de desenvolvimento"))

        # Authenticate user via Google OAuth
        print('Fazendo login no Google... ')
        token_file = ".user_token.json"
        user_email, user_id, user_creds = authenticate_google_user(
            FIREBASE_CLIENT_SECRETS_FILE,
            token_file)
        print(f"Usuário autenticado: {output.highlight(user_email)}")
        output.warning(f'Sessão salva em {output.highlight(token_file)}.'
                       ' Não compartilhe este arquivo!')

        # Initialize Firestore client using user OAuth credentials
        db_client = init_firebase_user_client(user_creds, FIREBASE_PROJECT_ID)
        print("Conexão com o Firebase Firestore iniciada")

        # Load  Moodle configuration
        moodle_config_data = load_moodle_config(config_file_path)
        MOODLE_BASE_URL = moodle_config_data['base_url']
        MOODLE_USERNAME = str(moodle_config_data['username'])
        sys.stdout.flush()
        if 'password' in moodle_config_data:
            MOODLE_PASSWORD = moodle_config_data['password']
        else:
            MOODLE_PASSWORD = getpass.getpass(("Digite sua senha do Moodle: "))

        print("Fazendo login no Moodle...")
        authenticated_session = login_moodle(MOODLE_USERNAME, MOODLE_PASSWORD,
                                             MOODLE_BASE_URL)

        print()
        for class_data in moodle_config_data['classes']:
            evidences = fetch_class_evidences(MOODLE_BASE_URL, class_data)

        if authenticated_session:
            print()
            for class_data in moodle_config_data['classes']:
                class_id = str(class_data["class_id"])
                print(f'Buscando dados da turma {class_id}...')
                class_info = fetch_class_information(MOODLE_BASE_URL, class_data)
                # evidences = fetch_evidences_information(MOODLE_BASE_URL, class_data)

                # Create class in Firestore
                if class_info:
                    create_class_in_firestore(db_client, user_email, class_info)
                    print(f"Turma {class_info['course_name']} criada com sucesso.")
                else:
                    output.warning(f"Turma {class_info['course_name']} ignorada.")

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        output.error(f"Falha ao carregar a configuração ({e})")
        sys.exit(1)
    except Exception as e:
        output.error(f"Falha inesperada ({e})")
        sys.exit(1)
