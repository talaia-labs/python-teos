import os
from multiprocessing import Process

from teos.teosd import main


from common.cryptographer import Cryptographer


def run_teosd(config, datadir):
    sk_file_path = os.path.join(datadir, "teos_sk.der")
    if not os.path.exists(sk_file_path):
        # Generating teos sk so we can return the teos_id
        teos_sk = Cryptographer.generate_key()
        Cryptographer.save_key_file(teos_sk.to_der(), "teos_sk", datadir)
    else:
        teos_sk = Cryptographer.load_private_key_der(Cryptographer.load_key_file(sk_file_path))

    teos_id = Cryptographer.get_compressed_pk(teos_sk.public_key)

    teosd_process = Process(target=main, kwargs={"config": config}, daemon=True)
    teosd_process.start()

    return teosd_process, teos_id


def build_appointment_data(commitment_tx_id, penalty_tx):
    appointment_data = {"tx": penalty_tx, "tx_id": commitment_tx_id, "to_self_delay": 20}

    return appointment_data
