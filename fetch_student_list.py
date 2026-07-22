"""
This script fetches the list of students for a specific class from a Moodle instance.
It extracts course details (discipline name, year, and term) along with student
identification numbers and names.
It uses credentials from a YAML configuration file and user input for the password.
"""

import requests
from bs4 import BeautifulSoup
import yaml
import getpass
import sys
import re


def load_moodle_config(config_file_path):
    """
    Loads Moodle configuration (base_url, username, and class_id) from a YAML file.

    Args:
        config_file_path (str): The path to the YAML configuration file.

    Returns:
        dict: A dictionary containing 'base_url', 'username', and 'class_id' for Moodle.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If there's an error parsing the YAML file.
        ValueError: If 'base_url' or 'username' or 'class_id' are missing in the Moodle section.
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        moodle_config = config.get('moodle', {})
        base_url = moodle_config.get('base_url')
        username = moodle_config.get('username')
        class_id = moodle_config.get('class_id')

        if not base_url or not username or not class_id:
            raise ValueError(
                f"Error: 'base_url', 'username', or 'class_id' not found in the 'moodle' section of {config_file_path}"
            )

        return {'base_url': base_url, 'username': username, 'class_id': class_id}

    except FileNotFoundError:
        raise FileNotFoundError(f"Error: The configuration file '{config_file_path}' was not found.")
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


OUTPUT_FILE = "student_list.txt"


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
        breadcrumb = soup.find('nav', attrs={'aria-label': re.compile(r'Navegação|Navigation', re.I)}) or soup.find('ul', class_='breadcrumb')
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


def fetch_student_list(session, moodle_base_url, class_id):
    """
    Fetches course metadata and the list of students for a given class ID,
    filtering by role 'Estudante' and status 'Ativo'.

    Args:
        session (requests.Session): An authenticated requests session.
        moodle_base_url (str): The base URL of the Moodle instance.
        class_id (int): The ID of the class to fetch the student list from.

    Returns:
        tuple: (dict containing course info, list of formatted strings "IdentificationNumber - Name")
    """
    initial_student_list_url = f"{moodle_base_url}/user/index.php?id={class_id}"
    filtered_students = set()

    print(f"Obtendo lista de alunos de: {initial_student_list_url}")

    try:
        full_list_url = f"{initial_student_list_url}&perpage=-1"

        print(f"Tentando obter a lista completa de alunos de: {full_list_url}")
        response = session.get(full_list_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        course_info = extract_course_info(soup)

        user_table = soup.find('table', id='participants')
        if not user_table:
            print("Erro: Não foi possível encontrar a tabela de participantes com id='participants'.")
            return course_info, []

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
            print(f"Erro: Não foi possível encontrar todas as colunas necessárias. Headers encontrados: {headers}")
            return course_info, []

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
                    status = status_div['data-status']
                else:
                    status = status_cell.get_text(strip=True)

                if roles.strip().lower() == "estudante" and status.strip().lower() == "ativo":
                    if full_name:
                        id_str = id_number if id_number else "N/A"
                        entry = f"{id_str} - {full_name}"
                        filtered_students.add(entry)

        if not filtered_students:
            print("Aviso: Nenhuma lista de alunos encontrada ou nenhum aluno corresponde aos critérios de filtragem.")

    except requests.exceptions.RequestException as e:
        print(f"Erro de requisição ao obter a lista de alunos: {e}")
        return {'course_name': 'Desconhecida', 'year': 'N/A', 'term': 'N/A'}, []
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao processar a lista de alunos: {e}")
        return {'course_name': 'Desconhecida', 'year': 'N/A', 'term': 'N/A'}, []

    sorted_students = sorted(list(filtered_students), key=lambda item: item.split(" - ", 1)[-1])
    return course_info, sorted_students


def save_student_list(course_info, students, output_file):
    """
    Saves course information and student list to a text file.

    Args:
        course_info (dict): Dictionary containing course metadata.
        students (list): A list of formatted student strings ("IdentificationNumber - Name").
        output_file (str): The path to the output file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Disciplina: {course_info['course_name']}\n")
            f.write(f"Ano: {course_info['year']}\n")
            f.write(f"Período: {course_info['term']}\n")
            f.write("-" * 40 + "\n")
            for student in students:
                f.write(f"{student}\n")
        print(f"Lista de alunos e dados do curso salvos em: {output_file}")
    except IOError as e:
        print(f"Erro ao salvar a lista de alunos no arquivo '{output_file}': {e}")


def main():
    config_file_path = "scraper_config.yaml"

    try:
        moodle_config_data = load_moodle_config(config_file_path)
        MOODLE_BASE_URL = moodle_config_data['base_url']
        MOODLE_USERNAME = moodle_config_data['username']
        MOODLE_CLASS_ID = moodle_config_data['class_id']

        MOODLE_PASSWORD = getpass.getpass("Digite sua senha do Moodle: ")

        print(f"Tentando fazer login no Moodle em {MOODLE_BASE_URL} com o usuário {MOODLE_USERNAME}...")
        authenticated_session = login_moodle(str(MOODLE_USERNAME), MOODLE_PASSWORD, MOODLE_BASE_URL)

        if authenticated_session:
            print("Login bem-sucedido. Obtendo lista de alunos e dados do curso...")
            course_info, students = fetch_student_list(authenticated_session, MOODLE_BASE_URL, MOODLE_CLASS_ID)

            print(f"\nDisciplina: {course_info['course_name']}")
            print(f"Ano: {course_info['year']}")
            print(f"Período: {course_info['term']}\n")

            if students:
                save_student_list(course_info, students, OUTPUT_FILE)
                print(f"Total de alunos filtrados: {len(students)}")
            else:
                print("Nenhum aluno encontrado ou erro ao obter a lista.")
        else:
            print("Não foi possível autenticar no Moodle.")

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        print(f"Erro de configuração: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()