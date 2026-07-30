"""
This script provides functionality to log into a Moodle instance using credentials
from a YAML configuration file and user input for the password.
It also authenticates the user via Google OAuth 2.0 to access Cloud Firestore.
"""
import datetime
import getpass
import os
import re
import sys
import uuid
from pprint import pprint

import requests
import yaml
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.cloud import firestore
from google.oauth2 import id_token
from google_auth_oauthlib.flow import InstalledAppFlow


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
        :param kwargs: Any additional keyword arguments to be passed to print()
        """
        print(f"{Output.YELLOW}Aviso{Output.RESET}: {text}", **kwargs)

    def error(self, text, **kwargs):
        """
        Prints an error message.
        :param text: Text to be printed
        :param kwargs: Any additional keyword arguments to be passed to print()
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

    :param config_file_path: The path to the YAML configuration file
    :return: A dictionary containing the configuration data
    :raises FileNotFoundError: If the configuration file does not exist
    :raises yaml.YAMLError: If there's an error parsing the YAML file
    :raises ValueError: If mandatory Moodle fields are missing
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

    :param config_file_path: The path to the YAML configuration file
    :return: A dictionary containing Firebase configuration parameters
    :raises FileNotFoundError: If the configuration file does not exist
    :raises yaml.YAMLError: If there's an error parsing the YAML file
    :raises ValueError: If mandatory configuration fields are missing
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
    Authenticates the user using Google OAuth 2.0 browser flow or cached credentials.

    :param client_secrets_file: Path to Google OAuth client secrets JSON file
    :param token_file: Path to store or read cached user credentials
    :return: Tuple of (user_email, user_id, credentials) of the authenticated user
    :raises FileNotFoundError: If the client secrets file does not exist
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

    :param user_credentials: The authenticated user credentials
    :param project_id: Firebase project ID
    :return: Firestore client instance acting on behalf of the user
    """
    return firestore.Client(project=project_id, credentials=user_credentials)


def login_moodle(username, password, moodle_url):
    """
    Performs login to a Moodle instance.

    :param username: The username for login
    :param password: The password for login
    :param moodle_url: The base URL of the Moodle instance
    :return: An authenticated requests session if login is successful, None otherwise
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
    Prompts for a password without echoing characters to the terminal.

    :param prompt: The prompt message to display
    :return: The entered password
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

    :param soup: Parsed HTML page
    :return: A dictionary containing 'course_name', 'year', and 'term', or None if unparseable
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
    Fetches the list of students for a given class ID, filtering by role 'Estudante'.

    :param session: An authenticated requests session
    :param moodle_base_url: The base URL of the Moodle instance
    :param class_id: The ID of the class to fetch the student list from
    :return: A list of dictionaries representing students
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
                        firestore_status = "ACTIVE" if moodle_status.strip().lower() == "ativo" else "CANCELLED"
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

    except requests.exceptions.RequestException:
        return []
    except Exception:
        return []

    # Sort students by name
    sorted_students = sorted(filtered_students, key=lambda student: student['name'])
    return sorted_students


def create_class_in_firestore(db_client, user_email, class_info):
    """
    Creates a class document and its 'students' subcollection in Firestore.

    :param db_client: Firestore client instance
    :param user_email: The authenticated user's email
    :param class_info: Dictionary containing class metadata and student list
    :return: The class ID of the created document
    """
    class_id = class_info['classId']
    student_list = class_info.get('studentList', [])

    class_doc = {
        'classId': class_id,
        'name': class_info['course_name'],
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


def create_evidences_in_firestore(db_client, user_email, class_id, evidences_list):
    """
    Creates or updates evidence documents in Firestore for a given class.

    :param db_client: Firestore client instance.
    :param user_email: The authenticated user's email.
    :param class_id: The ID of the class to which the evidences belong.
    :param evidences_list: A list of dictionaries, each representing an evidence.
    """
    if not evidences_list:
        return

    evidences_collection_ref = db_client.collection('users').document(user_email).collection(
        'classes').document(class_id).collection('evidences')

    for evidence_data in evidences_list:
        evidence_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{class_id}_{evidence_data['name']}"))

        evidence_doc = {
            'evidenceId': evidence_id,
            'classId': class_id,
            'name': evidence_data['name'],
            'deadline': evidence_data['deadline'],
            'type': evidence_data['type'],
            'scores': evidence_data['scores']
        }

        evidences_collection_ref.document(evidence_id).set(evidence_doc)

    print(f"  - {len(evidences_list)} documentos de evidência criados/atualizados.")


def fetch_gradebook_scores(session, moodle_base_url, class_id, gradebook_item_name, student_list):
    """
    Fetches scores for a specific gradebook item from the Moodle gradebook.

    :param session: An authenticated requests session.
    :param moodle_base_url: The base URL of the Moodle instance.
    :param class_id: The ID of the class to fetch the gradebook from.
    :param gradebook_item_name: The name of the gradebook item to extract scores for.
    :param student_list: A list of dictionaries, each representing a student with
        at least 'studentId' and 'name'.
    :return: A list of dictionaries, each containing 'student_id' and 'score' for the specified item.
             Returns an empty list if the gradebook item or scores cannot be found.
    """
    gradebook_url = f"{moodle_base_url}/grade/report/grader/index.php?id={class_id}"
    scores = []

    try:
        response = session.get(gradebook_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the gradebook table
        grade_table = soup.find('table',
                                class_='gradestable')  # Common class for Moodle grade tables
        if not grade_table:
            output.warning(f"Tabela de livro de notas não encontrada para a turma ID {class_id}.")
            return []

        # Find headers to locate the grade item column
        headers = [th.get_text(strip=True) for th in grade_table.find('thead').find_all('th')]
        grade_item_column_index = -1
        for i, header in enumerate(headers):
            if gradebook_item_name.lower() in header.lower():  # Case-insensitive match
                grade_item_column_index = i
                break

        if grade_item_column_index == -1:
            output.warning(f"Item do livro de notas '{gradebook_item_name}' não encontrado "
                           f"para a turma ID {class_id}.")
            return []

        # Create a mapping from student name (from Moodle) to our studentId
        student_name_to_id = {student['name'].lower(): student['studentId'] for student in
                              student_list}

        for row in grade_table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if not cells:  # Skip header rows or empty rows
                continue

            # Assuming student name is in the first column (index 0)
            student_name_cell = cells[0]
            student_name_link = student_name_cell.find('a')  # Student name is often a link
            moodle_student_name = student_name_link.get_text(
                strip=True) if student_name_link else student_name_cell.get_text(strip=True)

            # Find the corresponding studentId from our student_list
            student_id = student_name_to_id.get(moodle_student_name.lower())

            if student_id:
                # Extract score from the identified column
                if len(cells) > grade_item_column_index:
                    score_text = cells[grade_item_column_index].get_text(strip=True)
                    try:
                        score = float(
                            score_text.replace(',', '.'))  # Handle comma as decimal separator
                        scores.append({'student_id': student_id, 'score': score})
                    except ValueError:
                        output.warning(f"Não foi possível analisar a nota "
                                       f"'{score_text}' para o aluno {moodle_student_name} "
                                       "no item '{gradebook_item_name}'.")
                else:
                    output.warning(f"Célula de nota não encontrada para o aluno "
                                   f"{moodle_student_name} no item '{gradebook_item_name}'.")
            else:
                output.warning(f"Aluno '{moodle_student_name}' do livro de notas do "
                               "Moodle não encontrado na lista de alunos fornecida.")

    except requests.exceptions.RequestException as e:
        output.error(f"Falha ao buscar o livro de notas para a turma ID {class_id}: {e}")
        return []
    except Exception as e:
        output.error("Ocorreu um erro inesperado ao buscar as notas do "
                     f"livro de notas para a turma ID {class_id}: {e}")
        return []

    return scores


def fetch_quiz_scores(session, moodle_base_url, quiz_id, student_list):
    """
    Fetches final scores for a specific quiz for all students.

    :param session: An authenticated requests session.
    :param moodle_base_url: The base URL of the Moodle instance.
    :param quiz_id: The ID of the quiz.
    :param student_list: A list of dictionaries, each representing a student with at least
        'studentId' and 'name'.
    :return: A list of dictionaries, each containing 'student_id' and 'score' for the quiz.
             Returns an empty list if scores cannot be found.
    """
    quiz_report_url = f"{moodle_base_url}/mod/quiz/report.php?id={quiz_id}"
    scores = []

    try:
        response = session.get(quiz_report_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the quiz report table. This often has a specific class or ID.
        # Common classes include 'generaltable', 'flexible', 'quizattemptsummary'
        report_table = soup.find('table', class_='generaltable') or \
                       soup.find('table', class_='flexible') or \
                       soup.find('table', class_='quizattemptsummary')

        if not report_table:
            output.warning(f"Tabela de relatório do quiz não encontrada para o quiz ID {quiz_id}.")
            return []

        # Find headers to locate student name and final grade columns
        headers = [th.get_text(strip=True) for th in report_table.find('thead').find_all('th')]

        student_name_column_index = -1
        final_grade_column_index = -1

        for i, header in enumerate(headers):
            header_lower = header.lower()
            if "nome" in header_lower or "student name" in header_lower:
                student_name_column_index = i
            elif "nota final" in header_lower or "final grade" in header_lower:
                final_grade_column_index = i

        if student_name_column_index == -1 or final_grade_column_index == -1:
            output.warning(f"Colunas 'Nome do Aluno' ou 'Nota Final' não encontradas "
                           f"no relatório do quiz ID {quiz_id}.")
            return []

        # Create a mapping from student name (from Moodle) to our studentId
        student_name_to_id = {student['name'].lower(): student['studentId'] for student in
                              student_list}

        # Iterate through table rows (tbody)
        for row in report_table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if not cells:  # Skip header rows or empty rows
                continue

            # Extract student name from the appropriate column
            moodle_student_name = cells[student_name_column_index].get_text(strip=True)

            # Find the corresponding studentId from our student_list
            student_id = student_name_to_id.get(moodle_student_name.lower())

            if student_id:
                # Extract final grade from the appropriate column
                if len(cells) > final_grade_column_index:
                    grade_text = cells[final_grade_column_index].get_text(strip=True)
                    try:
                        # Moodle grades can be like "X.XX / Y.YY" or just "X.XX"
                        # We need to extract only the student's score
                        match = re.search(r'(\d[\d,\.]*)', grade_text)
                        if match:
                            score = float(match.group(1).replace(',', '.'))
                            scores.append({'student_id': student_id, 'score': score})
                        else:
                            output.warning("Não foi possível extrair a nota "
                                           f"numérica de '{grade_text}' para o aluno "
                                           f"{moodle_student_name} no quiz ID {quiz_id}.")
                    except ValueError:
                        output.warning(f"Não foi possível analisar a nota '{grade_text}' "
                                       f"para o aluno {moodle_student_name} no quiz ID {quiz_id}.")
                else:
                    output.warning("Célula de nota final não encontrada para o aluno "
                                   f"{moodle_student_name} no quiz ID {quiz_id}.")
            else:
                output.warning(f"Aluno '{moodle_student_name}' do relatório do quiz "
                               "não encontrado na lista de alunos fornecida.")

    except requests.exceptions.RequestException as e:
        output.error(f"Falha ao buscar a página de relatório do quiz para o quiz ID {quiz_id}: {e}")
        return []
    except Exception as e:
        output.error("Ocorreu um erro inesperado ao buscar "
                     f"as notas do quiz para o quiz ID {quiz_id}: {e}")
        return []

    return scores


def fetch_quiz_deadline(session, moodle_base_url, quiz_id):
    """
    Fetches the closing date (deadline) for a specific Moodle quiz.

    :param session: An authenticated requests session.
    :param moodle_base_url: The base URL of the Moodle instance.
    :param quiz_id: The ID of the quiz.
    :return: A datetime.date object representing the deadline, or None if not found.
    """
    quiz_view_url = f"{moodle_base_url}/mod/quiz/view.php?id={quiz_id}"
    try:
        response = session.get(quiz_view_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Common patterns for quiz deadlines in Moodle
        # Look for text like "Closing date" or "Available until"
        deadline_text_patterns = [
            re.compile(r'Closing date: (.+)'),
            re.compile(r'Available until: (.+)'),
            re.compile(r'Fechado em: (.+)'),
            re.compile(r'Disponível até: (.+)'),
        ]

        deadline_str = None
        # Search in specific elements that often contain this info
        for element in soup.find_all(['div', 'p', 'span', 'li']):
            text = element.get_text(strip=True)
            for pattern in deadline_text_patterns:
                match = pattern.search(text)
                if match:
                    deadline_str = match.group(1).strip()
                    break
            if deadline_str:
                break

        if deadline_str:
            # Attempt to parse various date formats
            date_formats = [
                "%d %B %Y, %H:%M %p",  # e.g., 25 December 2027, 12:00 AM
                "%d %B %Y, %H:%M",  # e.g., 25 December 2027, 12:00
                "%d %b %Y, %H:%M %p",  # e.g., 25 Dec 2027, 12:00 AM
                "%d %b %Y, %H:%M",  # e.g., 25 Dec 2027, 12:00
                "%A, %d %B %Y, %H:%M",  # e.g., Friday, 25 December 2027, 12:00
                "%d/%m/%Y %H:%M",  # e.g., 25/12/2027 12:00
            ]
            for fmt in date_formats:
                try:
                    # Moodle often uses locale-specific month names.
                    # For now, let's assume English month names for parsing,
                    # or try to handle Portuguese if it's common.
                    # This is a simplification and might need adjustment based on actual Moodle output.
                    deadline_str_en = deadline_str.replace('Janeiro', 'January').replace(
                        'Fevereiro', 'February').replace('Março', 'March').replace('Abril',
                                                                                   'April').replace(
                        'Maio', 'May').replace('Junho', 'June').replace('Julho', 'July').replace(
                        'Agosto', 'August').replace('Setembro', 'September').replace('Outubro',
                                                                                     'October').replace(
                        'Novembro', 'November').replace('Dezembro', 'December')

                    deadline_dt = datetime.datetime.strptime(deadline_str_en, fmt)
                    return deadline_dt.date()
                except ValueError:
                    continue
            output.warning(
                f"Não foi possível analisar a data limite '{deadline_str}' para o quiz ID {quiz_id}.")
            return None
        else:
            output.warning(f"Informações de data limite não encontradas para o quiz ID {quiz_id}.")
            return None

    except requests.exceptions.RequestException as e:
        output.error(f"Falha ao buscar a página do quiz para o quiz ID {quiz_id}: {e}")
        return None
    except Exception as e:
        output.error(
            f"Ocorreu um erro inesperado ao buscar a data limite do quiz para o quiz ID {quiz_id}: {e}")
        return None


def fetch_class_information(url, class_data):
    """
    Fetches course information and student list from Moodle.

    :param url: The base URL of the Moodle instance
    :param class_data: Dictionary containing class parameters
    :return: A dictionary with course information and student list, or None if extraction fails
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


def fetch_single_evidence(url, evidence_data, class_id, student_list):
    """
    Parses and fetches evidence details for a single assessment item.

    :param url: Moodle base URL
    :param evidence_data: Configuration information for an evidence item
    :param class_id: The ID of the class this evidence belongs to.
    :param student_list: The list of students for the current class.
    :return: Dictionary with processed evidence information or empty dict if invalid
    """
    evidence_information = {'name': evidence_data['title']}

    if 'gradebook_name' not in evidence_data and 'quiz_id' not in evidence_data:
        output.error(f"Dados insuficientes para '{evidence_data['title']}' - "
                     f"{output.highlight('gradebook_name')} ou {output.highlight('quiz_id')} necessárias")
        output.warning(f"Entrada '{evidence_data['title']}' ignorada.")
        return {}

    # Handle scores from gradebook
    if 'gradebook_name' in evidence_data:
        gradebook_name = evidence_data['gradebook_name']
        scores_list = fetch_gradebook_scores(authenticated_session, url,
                                                                class_id, gradebook_name,
                                                                student_list)
        if not scores_list:
            output.warning("Não foi possível obter notas do livro "
                           f"de notas para '{gradebook_name}'.")
            return {}
        evidence_information['scores'] = {item['student_id']: item['score'] for item in scores_list}


    # Handle scores from quiz
    elif 'quiz_id' in evidence_data:
        quiz_id = evidence_data['quiz_id']
        scores_list = fetch_quiz_scores(authenticated_session, url, quiz_id,
                                                           student_list)
        if not scores_list:
            output.warning(f"Não foi possível obter notas do quiz ID {quiz_id}.")
            return {}
        evidence_information['scores'] = {item['student_id']: item['score'] for item in scores_list}


    # Handle explicit deadline
    if 'deadline' in evidence_data:
        deadline = evidence_data['deadline']
        if not isinstance(deadline, datetime.date):
            output.error(f"{output.highlight('deadline')} não é uma data válida (AAAA-MM-DD).")
            output.warning(f"Entrada '{evidence_data['title']}' ignorada.")
            return {}
        deadline_dt = datetime.datetime.combine(deadline, datetime.datetime.min.time())
        evidence_information['deadline'] = int(deadline_dt.timestamp() * 1000)


    # Handle deadline from quiz
    elif 'deadline_quiz_id' in evidence_data:
        deadline_quiz_id = evidence_data['deadline_quiz_id']
        deadline = fetch_quiz_deadline(authenticated_session, url, deadline_quiz_id)
        if deadline:
            deadline_dt = datetime.datetime.combine(deadline, datetime.datetime.min.time())
            evidence_information['deadline'] = int(deadline_dt.timestamp() * 1000)
        else:
            output.warning(f"Não foi possível obter o prazo do quiz ID {deadline_quiz_id}.")
            return {}

    # If no deadline was found or explicitly set, and it's required, return empty
    if 'deadline' not in evidence_information:
        output.error(f"Em '{evidence_data['title']}' - "
                     f"Não há {output.highlight('deadline')} nem {output.highlight('deadline_quiz_id')}.")
        output.warning(f"Entrada '{evidence_data['title']}' ignorada.")
        return {}

    return evidence_information


def fetch_class_evidences(url, class_data):
    """
    Fetches all evidence items for a given class configuration.

    :param url: The base URL of the Moodle instance
    :param class_data: Class configuration dictionary
    :return: A list of dictionaries representing processed evidences
    """
    if "evidences" not in class_data:
        return []

    evidences_data = class_data['evidences']
    evidences_list = []
    class_id = class_data['class_id']
    student_list = class_data.get('studentList', [])  # Ensure student_list is available

    categories = [
        ('consolidation', 'CONSOLIDATION'),
        ('monitoring', 'MONITORING')
    ]

    for category_key, category_type in categories:
        if category_key in evidences_data:
            for item in evidences_data[category_key]:
                # Pass class_id and student_list to fetch_single_evidence
                evidence_info = fetch_single_evidence(url, item, class_id, student_list)
                if evidence_info:
                    evidence_info['type'] = category_type
                    evidences_list.append(evidence_info)

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

        # Load Moodle configuration
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

        if authenticated_session:
            print()
            for class_data in moodle_config_data['classes']:
                class_id = str(class_data["class_id"])
                print(f'Buscando dados da turma {class_id}...')
                class_info = fetch_class_information(MOODLE_BASE_URL, class_data)

                # Update class_data with student_list before fetching evidences
                if class_info:
                    class_data['studentList'] = class_info['studentList']

                    # Create class in Firestore
                    create_class_in_firestore(db_client, user_email, class_info)
                    print(f"Turma {class_info['course_name']} criada com sucesso.")

                    evidences = fetch_class_evidences(MOODLE_BASE_URL, class_data)
                    if evidences:
                        create_evidences_in_firestore(db_client, user_email, class_id, evidences)

                else:
                    output.warning(
                        f"Turma {class_id} ignorada. Não foi possível obter informações da turma.")

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        output.error(f"Falha ao carregar a configuração ({e})")
        sys.exit(1)
    except Exception as e:
        output.error(f"Falha inesperada ({e})")
        sys.exit(1)
