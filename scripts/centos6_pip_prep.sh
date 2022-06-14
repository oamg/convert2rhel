#!/usr/bin/env bash

# The SSL implementation that python-2.6 uses is insecure and pip refuses to install
# packages using it. This script will use curl to download the packages securely and
# then pip can be asked to install from the local files

links=(
    "https://files.pythonhosted.org/packages/3a/05/f4936fde0aa8ce3b646b6014c59417c8cc7c1958df41e05bc77fcb098743/scandir-0.4.zip"
    "https://files.pythonhosted.org/packages/94/4a/db842e7a0545de1cdb0439bb80e6e42dfe82aaeaadd4072f2263a4fbed23/funcsigs-1.0.2.tar.gz"
    "https://files.pythonhosted.org/packages/09/4f/89b06c7fdc09687bca507dc411c342556ef9c5a3b26756137a4878ff19bf/coverage-3.7.1.tar.gz"
    "https://files.pythonhosted.org/packages/18/dd/e617cfc3f6210ae183374cd9f6a26b20514bbb5a792af97949c5aacddf0f/argparse-1.4.0.tar.gz"
    "https://files.pythonhosted.org/packages/2a/a5/139ca93a9ffffd9fc1d3f14be375af3085f53cc490c508cf1c988b886baa/py-1.4.33.tar.gz"
    "https://files.pythonhosted.org/packages/e0/e5/36c349db721aac9a76ec1b40dd6aa48855aa600f11f7fab11655b7463dd2/logilab-common-0.53.0.tar.gz"
    "https://files.pythonhosted.org/packages/b8/2d/b8a38176b243617b1e36144a905c1892325b0b0079f142e3ae3f0b14cfe4/pbr-1.3.0.tar.gz"
    "https://files.pythonhosted.org/packages/d6/1b/1850d5174bf770cfcb3fda651e68b43e0b610d43e13a0d95a250457b9bf9/setuptools_scm-1.5.2.tar.gz"
    "https://files.pythonhosted.org/packages/09/69/cf252f211dbbf58bbbe01a3931092d8a8df8d55f5fe23ac5cef145aa6468/pylint-1.1.0.tar.gz"
    "https://files.pythonhosted.org/packages/b0/ac/dbbfed5f086b61ace9e70d821b524c888cebf5512b147985876ef1b09cd1/astroid-1.2.0.tar.gz"
    "https://files.pythonhosted.org/packages/69/4e/ba9d0ccf3d4132abefdaac222c396f9c6f00537218fd15611e675f7a1e6d/unittest2-0.5.1.zip"
    "https://files.pythonhosted.org/packages/1f/f8/8cd74c16952163ce0db0bd95fdd8810cbf093c08be00e6e665ebf0dc3138/pytest-3.2.5.tar.gz"
    "https://files.pythonhosted.org/packages/24/b4/7290d65b2f3633db51393bdf8ae66309b37620bc3ec116c5e357e3e37238/pytest-cov-2.5.1.tar.gz"
    "https://files.pythonhosted.org/packages/0c/53/014354fc93c591ccc4abff12c473ad565a2eb24dcd82490fae33dbf2539f/mock-2.0.0.tar.gz"
    "https://files.pythonhosted.org/packages/f2/2b/2faccdb1a978fab9dd0bf31cca9f6847fbe9184a0bdcc3011ac41dd44191/pytest-catchlog-1.2.2.zip"
    "https://files.pythonhosted.org/packages/94/d8/65c86584e7e97ef824a1845c72bbe95d79f5b306364fa778a3c3e401b309/pathlib2-2.3.5.tar.gz"
    )

for link in ${links[@]}; do
    curl $link -o ${link##*\/}
done
