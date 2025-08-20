import psycopg2
import logging
import os
from utils.common import get_secret_from_key_vault
PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
POSTGRESQL_PWD = os.environ.get("POSTGRESQL_PWD")
PGDB_PASSWORD = get_secret_from_key_vault(POSTGRESQL_PWD)
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = os.environ.get("PGDB_DBNAME")
VERSION_TABLE_NAME = os.environ.get("VERSION_TABLE_NAME")
LOG_TABLE_NAME = os.environ.get("LOG_TABLE_NAME")
PGDB_QSET_SETTING_TABLE_NAME = os.environ.get("PGDB_QSET_SETTING_TABLE_NAME")
PGDB_QSET_TABLE_NAME = os.environ.get("PGDB_QSET_TABLE_NAME")

def check_last_version(system_name = None):
    try:
        QUERY = f"""SELECT 
            system_name
            ,seed_cont_last_version
            ,local_last_version
            ,integration_last_version
            ,search_cont_last_version
            ,seed_cont_name
            FROM {VERSION_TABLE_NAME}
            WHERE
            1=1
        """
        if system_name is not None:
            QUERY += f"AND system_name = '{system_name}';"
        else:
            QUERY += ";"
        # PostgreSQL 데이터베이스에 연결
        
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY)
        logging.info("[query execute] " + QUERY)
        return cursor.fetchall()
    except Exception as error:
        logging.info("Error while executing to query", error)
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()
            
def update_last_version(index_type,system_name,version):
    try:
        QUERY = f"""UPDATE {VERSION_TABLE_NAME}
            SET
            {index_type}_last_version={version},
            {index_type}_last_updated=NOW()
            WHERE 
            system_name='{system_name}';
        """
        # PostgreSQL 데이터베이스에 연결
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY)
        logging.info("[query execute] " + QUERY)
        connection.commit()
    except Exception as error:
        logging.info("Error while executing to query", error)
        logging.info("Error while executing to query", error)
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()
            
def history_insert(work_type,system_name,version,count,error=None):
    try:
        QUERY = f"""INSERT INTO {LOG_TABLE_NAME} (
            system_name, work_type, version, debug_count, error_message)
	        VALUES (%s, %s, %s, %s, %s)
        """
        # PostgreSQL 데이터베이스에 연결
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY, (system_name, work_type, version, count, error))
        # print(QUERY)
        logging.info("[query execute] " + QUERY)
        logging.info("history inserted")
        connection.commit()
    except Exception as error:
        # print(f"error : {error}")
        logging.info("Error while executing to query", error)
        logging.info("Error while executing to query", error)
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()           
            
def check_delete_version(system_name=None):
    try:
        system_name_condition = f"AND system_name = '{system_name}'" if system_name else ""
        QUERY = f"""
            WITH ranked_versions AS (
                SELECT *,
                    ROW_NUMBER() OVER (PARTITION BY system_name ORDER BY version DESC) AS rn_version
                FROM (
                    SELECT DISTINCT ON (system_name, version, updated) *
                    FROM public.{LOG_TABLE_NAME}
                    WHERE work_type = 'SEARCH' AND debug_count > 0
                    {system_name_condition}
                    ORDER BY system_name, updated DESC
                ) AS distinct_versions
            )
            SELECT *
            FROM ranked_versions
            WHERE rn_version = 4 OR (rn_version = (SELECT MAX(rn_version) FROM ranked_versions rv WHERE rv.system_name = ranked_versions.system_name) AND NOT EXISTS (
                SELECT 1
                FROM ranked_versions rv
                WHERE rv.system_name = ranked_versions.system_name AND rv.rn_version = 4
            ));

        """
        
        # QUERY = base_query.format(system_name_condition=system_name_condition, LOG_TABLE_NAME = LOG_TABLE_NAME)
        # PostgreSQL 데이터베이스에 연결
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY)
        logging.info("[query execute] " + QUERY)
        return cursor.fetchall()
    except Exception as error:
        logging.info("Error while executing to query", error)
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()


def get_verification_setting_by_system(system_name):
    try:
        QUERY = f"""
            SELECT
                system_name,
                code_mapping_flag,
                index_verification_field
            FROM {PGDB_QSET_SETTING_TABLE_NAME}
            WHERE system_name = %s
        """
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY, (system_name,))
        logging.info(f"[query execute] {QUERY} with system_name = {system_name}")
        result = cursor.fetchall()
        logging.info(f"Query result: {result}")
        return result
    except Exception as error:
        logging.exception("Error while executing query")
        return None
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()


def get_pending_verification_qaset_by_system(system_name,target_version):
    try:
        QUERY = f"""
            SELECT
                filter_system_name,
                filter_version,
                filter_category1,
                filter_category2,
                filter_category3,
                filter_modelcode,
                index_verification_value,
                verification_inserted,
                verification_executed_flag,
                verification_executed
            FROM {PGDB_QSET_TABLE_NAME}
            WHERE filter_system_name = %s
                and filter_version = %s
              AND verification_executed_flag = 0
        """
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY, (system_name, target_version))
        logging.info(f"[query execute] {QUERY} with system_name = {system_name}")
        result = cursor.fetchall()
        logging.info(f"Query result: {result}")
        return result
    except Exception as error:
        logging.exception("Error while executing query")
        return None
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()
            
def get_qaset_mapping_code_by_system(system_name,target_version):
    try:
        QUERY = f"""
            SELECT DISTINCT            
                filter_category1,
                filter_category2,
                filter_category3,
                filter_modelcode
            FROM {PGDB_QSET_TABLE_NAME}
            WHERE filter_system_name = %s 
                AND filter_version = %s
        """
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY, (system_name, target_version))
        logging.info(f"[query execute] {QUERY} with system_name = {system_name}")
        result = cursor.fetchall()
        logging.info(f"Query result: {result}")
        return result
    except Exception as error:
        logging.exception("Error while executing query")
        return None
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()


def get_all_verification_settings():
    try:
        QUERY = f"""
            SELECT
                system_name,
                code_mapping_flag,
                index_verification_field
            FROM {PGDB_QSET_SETTING_TABLE_NAME}
        """
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY)
        logging.info("[query execute] " + QUERY)
        result = cursor.fetchall()
        logging.info(f"Query result: {result}")
        return result
    except Exception as error:
        logging.exception("Error while executing query")
        return None  # 또는 [] 로 처리해도 됨
    finally:
        if connection:
            logging.info("success db conn close")
            cursor.close()
            connection.close()


def rollback_seed_version_to_local(system_name, local_version):
    try:
        QUERY = f"""
            UPDATE {VERSION_TABLE_NAME}
            SET seed_cont_last_version = {local_version},
                seed_cont_last_updated = NOW()
            WHERE system_name = '{system_name}';
        """
        connection = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = connection.cursor()
        cursor.execute(QUERY)
        logging.info(f"[rollback] Rolled back seed version to local version {local_version} for {system_name}")
        connection.commit()
    except Exception as error:
        logging.info(f"[rollback] Error during rollback for {system_name}: {error}")
    finally:
        if connection:
            cursor.close()
            connection.close()


def update_qaset_verification_result(system_name, version, verification_value, flag):
    try:
        conn = psycopg2.connect(
            user=PGDB_USERNAME,
            password=PGDB_PASSWORD,
            host=PGDB_HOST,
            dbname=PGDB_DBNAME
        )
        cursor = conn.cursor()
        query = f"""
        UPDATE {PGDB_QSET_TABLE_NAME}
        SET
            verification_executed_flag = %s,
            verification_executed = now()
        WHERE
            filter_system_name = %s
            AND filter_version = %s
            AND index_verification_value = %s;
        """
        cursor.execute(query, (flag, system_name, version, verification_value))
        conn.commit()
        logging.info(f"[{version}] QASET verification update complete. Flag={flag}")
    except Exception as e:
        logging.warning(f"[{version}] Failed to update QASET result: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()