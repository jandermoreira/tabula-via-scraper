"""
This script seeds the Cloud Firestore database with fake data for testing purposes.

It generates users, classes, students, and evidences according to the schema
defined in firestore.md. The data generation is deterministic based on the
provided classId to ensure that subsequent runs update existing documents
instead of creating new ones.
"""
import random
import sys
import uuid
from datetime import datetime, timedelta
from pprint import pprint

import yaml

# The main scraper script has a hyphen in its name, which is not a valid
# identifier for a direct import. We use __import__ to load it dynamically.
scraper = __import__("tabula-via-scraper")
Output = scraper.Output
authenticate_google_user = scraper.authenticate_google_user
init_firebase_user_client = scraper.init_firebase_user_client

output = Output()


def generate_fake_students(class_id, num_students):
    """
    Generates a deterministic list of fake students for a given class.

    :param class_id: The unique identifier for the class.
    :param num_students: The number of students to generate.
    :return: A list of dictionaries, where each dictionary represents a student.
    """
    students = []
    random.seed(class_id)
    namespace = uuid.uuid5(uuid.NAMESPACE_DNS, class_id)
    # statuses = ['ACTIVE', 'INACTIVE', 'CANCELLED']
    # status_distribution = random.choices(statuses, weights=[0.85, 0.1, 0.05], k=num_students)

    for i in range(1, num_students + 1):
        student_name = f"Student {i:02d}"
        student_id = str(uuid.uuid5(namespace, str(i)))
        student_data = {
            'studentId': student_id,
            'name': student_name,
            'displayName': "",
            'studentNumber': f"{random.randint(810000, 899999)}",
            'classId': class_id,
            'status': 'ACTIVE',
        }
        students.append(student_data)
    return sorted(students, key=lambda s: s['name'])


def generate_fake_evidences(class_id, num_cycles):
    """
    Generates a deterministic, chronological list of fake evidences.

    :param class_id: The unique identifier for the class.
    :param num_cycles: The number of assessment cycles to generate.
    :return: A list of dictionaries, where each dictionary represents an evidence.
    """
    random.seed(class_id)
    namespace = uuid.uuid5(uuid.NAMESPACE_DNS, class_id)
    evidences = []

    start_date = datetime(2024, 8, 5)
    current_date = start_date

    l_counter = 1
    p_counter = 1

    for _ in range(num_cycles):
        num_ls = random.randint(2, 4)
        for _ in range(num_ls):
            name = f"L{l_counter}"
            evidence_id = str(uuid.uuid5(namespace, name))
            evidences.append({
                'evidenceId': evidence_id,
                'name': name,
                'type': 'MONITORING',
                'deadline': int(current_date.timestamp() * 1000),
            })
            l_counter += 1
            current_date += timedelta(days=7)

        name = f"P{p_counter}"
        evidence_id = str(uuid.uuid5(namespace, name))
        evidences.append({
            'evidenceId': evidence_id,
            'name': name,
            'type': 'CONSOLIDATION',
            'deadline': int(current_date.timestamp() * 1000),
        })
        p_counter += 1
        current_date += timedelta(days=7)

    return evidences


def _get_student_score(student, evidence, class_id):
    """
    Calculates a deterministic score for a student-evidence pair.

    :param student: The student dictionary.
    :param evidence: The evidence dictionary.
    :param class_id: The class ID for seeding.
    :return: A float score or None if the student "missed" the activity.
    """
    # Combine student and evidence IDs with the class_id to create a unique seed
    seed_str = f"{class_id}-{student['studentId']}-{evidence['evidenceId']}"
    random.seed(seed_str)

    # Decide if the student "missed" this activity (e.g., 5% chance)
    if random.random() < 0.05:
        return None

    # Generate a score based on the evidence type
    if evidence['type'] == 'MONITORING':
        # Monitoring activities are scored from 0.0 to 10.0
        return round(random.uniform(5.0, 10.0), 2)
    elif evidence['type'] == 'CONSOLIDATION':
        # Consolidation activities are also scored from 0.0 to 10.0
        return round(random.uniform(4.0, 9.5), 2)

    return None


def generate_scores_for_scenario(students, evidences, class_id, scenario):
    """
    Generates scores for evidences based on a class scenario.

    :param students: The list of students in the class.
    :param evidences: The list of evidences for the class.
    :param class_id: The class ID for seeding.
    :param scenario: 'BEGINNING', 'MIDDLE', or 'COMPLETE'.
    :return: The evidences list updated with a 'scores' map.
    """
    # Define the percentage of evidences that should have scores for each scenario
    scenario_percentages = {
        'BEGINNING': 0.25,
        'MIDDLE': 0.55,
        'COMPLETE': 1.0,
    }

    # Validate the provided scenario
    if scenario not in scenario_percentages:
        raise ValueError(f"Invalid scenario: {scenario}. Must be one of {list(scenario_percentages.keys())}")

    # Determine the number of evidences that will have scores
    num_evidences_with_scores = int(len(evidences) * scenario_percentages[scenario])

    # Iterate through all evidences
    for i, evidence in enumerate(evidences):
        # Initialize the scores map for every evidence
        evidence['scores'] = {}

        # Check if the current evidence is active for this scenario
        if i < num_evidences_with_scores:
            # Iterate through each student to generate their score
            for student in students:
                # Skip students who are not active
                if student['status'] != 'ACTIVE':
                    continue

                # Get the score for the student-evidence pair
                score = _get_student_score(student, evidence, class_id)

                # Add the score to the map if it's not None
                if score is not None:
                    evidence['scores'][student['studentId']] = score

    return evidences


def print_structured_evidences(evidences):
    """
    Prints a list of evidences in a structured, cycle-based format.

    :param evidences: A list of evidence dictionaries.
    """
    print(f"\n--- Generated {len(evidences)} evidences (Structured View) ---")
    cycle_num = 1
    current_cycle_evidences = []
    for evidence in evidences:
        current_cycle_evidences.append(evidence)
        if evidence['type'] == 'CONSOLIDATION':
            print(f"\n{output.CYAN}Cycle {cycle_num}{output.RESET}")
            for item in current_cycle_evidences:
                deadline_dt = datetime.fromtimestamp(item['deadline'] / 1000)
                deadline_str = deadline_dt.strftime('%Y-%m-%d')
                type_str = f"({item['type']})"
                print(f"  - {item['name']:<4} {type_str:<15} Deadline: {deadline_str}  ID: {item['evidenceId']}")
            current_cycle_evidences = []
            cycle_num += 1


def create_or_update_class(db_client, user_email, class_id, num_students, num_cycles, scenario):
    """
    Creates or updates a class, its students, and its evidences in Firestore.

    :param db_client: An authenticated Firestore client instance.
    :param user_email: The email of the user to whom the data will be associated.
    :param class_id: The unique identifier for the class.
    :param num_students: The number of students to generate for this class.
    :param num_cycles: The number of assessment cycles to generate.
    :param scenario: The scenario for score generation ('BEGINNING', 'MIDDLE', 'COMPLETE').
    """
    print(f"\n{output.BOLD}Processing class: {output.highlight(class_id)} with scenario: {output.highlight(scenario)}{output.RESET}")

    # 1. Generate all data deterministically
    class_data = {
        'classId': class_id,
        'name': f"Disicplina de Teste ({class_id})",
        'academicYear': "2024",
        'period': "1",
        'numberOfSessions': 20,
    }
    students = generate_fake_students(class_id, num_students)
    evidences = generate_fake_evidences(class_id, num_cycles)
    evidences_with_scores = generate_scores_for_scenario(students, evidences, class_id, scenario)

    # 2. Get Firestore references
    class_ref = db_client.collection('users').document(user_email).collection('classes').document(class_id)
    students_collection_ref = class_ref.collection('students')
    evidences_collection_ref = class_ref.collection('evidences')

    # 3. Write data to Firestore
    class_ref.set(class_data)
    print(f"  - Class document '{class_id}' created/updated.")

    for student in students:
        students_collection_ref.document(student['studentId']).set(student)
    print(f"  - {len(students)} student documents created/updated.")

    for evidence in evidences_with_scores:
        evidences_collection_ref.document(evidence['evidenceId']).set(evidence)
    print(f"  - {len(evidences_with_scores)} evidence documents created/updated.")


def get_dev_firebase_config(config_file_path):
    """
    Loads Firebase configuration and forces it to the 'dev' environment.
    ... (docstring from previous version)
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file '{config_file_path}' not found.")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error processing YAML file '{config_file_path}': {e}")

    firebase_config = config.get('firebase', {})
    environments = firebase_config.get('environments', {})

    if 'dev' not in environments:
        raise ValueError("The 'dev' environment is not defined in the Firebase configuration.")

    dev_config = environments['dev']

    if 'project_id' not in dev_config or 'client_secrets_file' not in dev_config:
        raise ValueError("The 'dev' environment is missing 'project_id' or 'client_secrets_file'.")

    return dev_config


def main():
    """
    Main function to authenticate and run the seeding process.
    """
    config_file_path = "scraper_config.yaml"

    classes_to_seed = [
        {"class_id": "1055001", "num_students": 5, "num_cycles": 2, "scenario": "BEGINNING"},
        {"class_id": "1055002", "num_students": 10, "num_cycles": 3, "scenario": "MIDDLE"},
        {"class_id": "1055003", "num_students": 20, "num_cycles": 4, "scenario": "COMPLETE"},
    ]

    try:
        output.warning(f"Forcing the use of the {output.highlight('development')} environment.")
        firebase_dev_config = get_dev_firebase_config(config_file_path)

        project_id = firebase_dev_config['project_id']
        client_secrets_file = firebase_dev_config['client_secrets_file']

        print('Authenticating with Google...')
        token_file = ".user_token.json"
        user_email, _, user_creds = authenticate_google_user(
            client_secrets_file,
            token_file
        )
        print(f"Authenticated as: {output.highlight(user_email)}")

        db_client = init_firebase_user_client(user_creds, project_id)
        print(f"Firestore client initialized for project: {output.highlight(project_id)}")

        for class_info in classes_to_seed:
            create_or_update_class(
                db_client,
                user_email,
                class_info["class_id"],
                class_info["num_students"],
                class_info["num_cycles"],
                class_info["scenario"]
            )

        print(f"\n{output.GREEN}Fake data seeding process finished successfully.{output.RESET}")

    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        output.error(f"Configuration or authentication failed: {e}")
        sys.exit(1)
    except ImportError as e:
        output.error(f"Failed to import from 'tabula-via-scraper.py': {e}")
        output.warning("Please ensure the script is in the same directory.")
        sys.exit(1)
    except Exception as e:
        output.error(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
