"""Download the public datasets used for external validation, pinned by SHA-256 (not shipped in the repo).

    python scripts/fetch_external_data.py

ar_ibm_sample.csv: IBM Watson Analytics sample "Accounts Receivable" data (2,466 invoices, 100 customers,
5 country codes, 2012-2013), as mirrored on GitHub. Public sample data of unknown origin: used to test
whether CashBridge's payment models generalise beyond its own synthetic history, not as SME ground truth.

polish_{1..5}year.arff: Polish Companies Bankruptcy (Tomczak 2016, UCI ML Repository, doi:10.24432/C5F600, CC BY 4.0),
mirrored on GitHub because the UCI site is not reachable from the build environment. The mirror was checked against the
counts UCI publishes (companies / bankrupt: 7027/271, 10173/400, 10503/495, 9792/515, 5910/410) and is pinned by SHA-256.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS = {
    "polish_1year.arff": ("https://raw.githubusercontent.com/kamileyagci/project-bankruptcy-prediction/master/data/1year.arff",
                           "978ce71a4809e964dda43d46a368c27a1a36df1e0b6345f215473ec9c3b12add"),
    "polish_2year.arff": ("https://raw.githubusercontent.com/kamileyagci/project-bankruptcy-prediction/master/data/2year.arff",
                           "ec67460055735857b84a73d961193e2b7313147c1b93d900f08400e4071bdb7c"),
    "polish_3year.arff": ("https://raw.githubusercontent.com/kamileyagci/project-bankruptcy-prediction/master/data/3year.arff",
                           "662617d2f90bfd17223595e50a0ac7007f9ee7915cfb519dee0422b31dd13ebc"),
    "polish_4year.arff": ("https://raw.githubusercontent.com/kamileyagci/project-bankruptcy-prediction/master/data/4year.arff",
                           "ae11434f0823d6208142ac5a4e83b4f3d7bcf4e827b330a798fdd6590bd9f5cb"),
    "polish_5year.arff": ("https://raw.githubusercontent.com/kamileyagci/project-bankruptcy-prediction/master/data/5year.arff",
                           "cb3f6f250ac46bd8d18e9a222f489fe8ee3e396fcec18959f5a0ef8e8169b2fc"),
    "ar_ibm_sample.csv": ("https://raw.githubusercontent.com/pthiagu2/DataMining/master/WA_Fn-UseC_-Accounts-Receivable.csv",
                          "f5d488eaa4c1cc843b478b6f1068c553c5394aab4b64d587e4b9ad811d845c19"),
}


def path(name: str) -> Path:
    return ROOT / "data" / "external" / name


def fetch(name: str) -> Path:
    url, sha = DATASETS[name]
    target = path(name)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = urllib.request.urlopen(url, timeout=60).read()
    got = hashlib.sha256(raw).hexdigest()
    if got != sha:
        raise SystemExit(f"{name}: SHA-256 {got} does not match the pinned {sha}; refusing to use it")
    target.write_bytes(raw)
    return target


if __name__ == "__main__":
    for n in DATASETS:
        print(fetch(n))
    sys.exit(0)
