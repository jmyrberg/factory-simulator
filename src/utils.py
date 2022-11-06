"""Module for utility functions and classes."""


import logging

from concurrent.futures import ThreadPoolExecutor, wait

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


def dt2ts(dt):
    return int(pd.to_datetime(dt).timestamp() * 1000)


def run_concurrently(func, args_list, max_workers=None):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        res = [executor.submit(func, *args) for args in args_list]
        wait(res)

    return res


def upsert_data(db, df, model, key):
    values = df.replace({np.nan: None}).set_index(key).to_dict('index')
    entries_to_update = []
    entries_to_insert = []

    # get all entries to be updated
    n_updates = 0
    for each in (
            db.query(model)
            .filter(getattr(model, key).in_(values.keys())).all()):
        key_value = str(getattr(each, key))
        entry = values.pop(key_value)
        entries_to_update.append({key: key_value, **entry})
        n_updates += 1

    # get all entries to be inserted
    n_inserts = 0
    for key_value, entry in values.items():
        entries_to_insert.append({key: key_value, **entry})
        n_inserts += 1

    db.bulk_insert_mappings(model, entries_to_insert)
    db.bulk_update_mappings(model, entries_to_update)

    try:
        db.commit()
        logger.info(f'Updated database with {n_inserts} inserts and '
                    f'{n_updates} updates')
    except Exception as e:
        logger.error(f'Failed to update database: {str(e)}, rolling back')
        db.rollback()
        db.flush()
        logger.info('Rollback successful')
