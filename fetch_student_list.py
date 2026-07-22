"""
This script fetches the list of students for a specific class from a Moodle instance.
It extracts student identification numbers from the "Número de identificação" column
and returns them formatted as "ID - Name".
It uses credentials from a YAML configuration file and user input for the password.
"""

import requests
from bs4 import BeautifulSoup
import yaml
import getpass
import sys


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


def fetch_student_list(session, moodle_base_url, class_id):
    """
    Fetches the list of students for a given class ID, filtering by role 'Estudante' and status 'Ativo'.
    Retrieves the value from the 'Número de identificação' column to precede each student's name.

    Args:
        session (requests.Session): An authenticated requests session.
        moodle_base_url (str): The base URL of the Moodle instance.
        class_id (int): The ID of the class to fetch the student list from.

    Returns:
        list: A list of formatted strings "IdentificationNumber - Name", sorted by name.
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

        user_table = soup.find('table', id='participants')
        if not user_table:
            print("Erro: Não foi possível encontrar a tabela de participantes com id='participants'.")
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
            print(f"Erro: Não foi possível encontrar todas as colunas necessárias. Headers encontrados: {headers}")
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
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao processar a lista de alunos: {e}")

    return sorted(list(filtered_students), key=lambda item: item.split(" - ", 1)[-1])


def save_student_list(students, output_file):
    """
    Saves the list of student names to a text file, one student per line.

    Args:
        students (list): A list of formatted student strings ("IdentificationNumber - Name").
        output_file (str): The path to the output file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for student in students:
                f.write(f"{student}\n")
        print(f"Lista de alunos salva em: {output_file}")
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
            print("Login bem-sucedido. Obtendo lista de alunos...")
            students = fetch_student_list(authenticated_session, MOODLE_BASE_URL, MOODLE_CLASS_ID)

            if students:
                save_student_list(students, OUTPUT_FILE)
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