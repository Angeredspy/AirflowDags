from airflow import DAG
from datetime import datetime
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.sensors.http import HttpSensor #Executes a HTTP GET statement and returns False on failure
from airflow.providers.http.operators.http import SimpleHttpOperator #Use the SimpleHttpOperator to call HTTP requests and get the response text back.
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

from pandas import json_normalize 

import json

def _process_user(ti): #ti represents a task instance
    user = ti.xcom_pull(task_ids='extract_user')
    user = user['results'][0]
    processed_user = json_normalize({
        'firstName': user['name']['first'],
        'lastName': user['name']['last'],
        'country': user['location']['country'],
        'username': user['login']['username'],
        'password': user['login']['password'],
        'email': user['email']
    })
    processed_user.to_csv('/tmp/processed_user.csv',index=None, header=False)

def _store_user():
    #This hook will be used to copy the users within the filename to the users table created with PostgresOperator
    hook = PostgresHook(postgres_conn_id='postgres')
    #The copy_expert method in the PostgresHook of Apache Airflow is used to execute the COPY statement in PostgreSQL
    #This method is not available with the PostgresOperator! 
    hook.copy_expert(
        sql="COPY users FROM stdin WITH DELIMITER AS ','",
        filename='/tmp/processed_user.csv'
    )

with DAG('user_processing', start_date=datetime(2022, 1, 1), 
    schedule_interval='@daily', catchup=False) as dag:

    create_table = PostgresOperator(
        task_id='create_table',
        postgres_conn_id='postgres',
        sql='''
        CREATE TABLE IF NOT EXISTS users (
            firstName TEXT NOT NULL,
            lastName TEXT NOT NULL,
            country TEXT NOT NULL,
            username TEXT NOT NULL, 
            password TEXT NOT NULL,
            email TEXT NOT NULL
        );
    '''
    )

    is_api_available = HttpSensor(
        task_id='is_api_available',
        http_conn_id='user_api',
        endpoint='api/'
    )

    extract_user = SimpleHttpOperator(
        task_id='extract_user',
        http_conn_id='user_api',
        endpoint='api/',
        method='GET',
        response_filter= lambda response: json.loads(response.text),
        log_response=True
    )

    process_user = PythonOperator(
        task_id='process_user',
        python_callable=_process_user #python_callable is the python function to execute within the PyOp
    )

    store_user = PythonOperator(
        task_id='store_user',
        python_callable=_store_user
    )

    create_table >> is_api_available >> extract_user >> process_user >> store_user