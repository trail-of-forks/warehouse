---
title: Getting started
---

# Signing release with Attestations

!!! note
  
    Signing a release with attestations requires setting up [Trusted Publishers]
  

!!! warning

    The following document only describes the procedure for GitHub Actions.


## They easy way

If you are already using the PyPA's `pypi-publish` action to publish
your packages, the only change you need to also sign them is to add the 
following yaml :

```yaml
attestations: true
```

So, in the end, your action might look like something like this :

<!-- TODO(dm): Change the version in the following snippet once the action 
has been updated -->

```yaml hl_lines="14-15"
jobs:
  pypi-publish:
    name: upload release to PyPI
    runs-on: ubuntu-latest
    # Specifying a GitHub environment is optional, but strongly encouraged
    environment: release
    permissions:
      # IMPORTANT: this permission is mandatory for trusted publishing
      id-token: write
    steps:
      # retrieve your distributions here
      - name: Publish package distributions to PyPI
        uses: pypa/gh-action-pypi-publish@release/vXXXX
        with:
          attestations: true
```

## The manual way

!!! warning

    **STOP! You probably don't need this section; it exists only to provide 
    some internal details about how GitHub Actions and PyPI coordinate using
    OIDC. If you're an ordinary user, it is strongly recommended that you use 
    the PyPA's pypi-publish action instead. **


The process for signing an artifact requires an OIDC token. This procedure 
is described in the [Trusted Publishers] section.

The process is then as followed : 

1. Configure the environment
2. Lists every artifact that needs to be signed
3. Generate an attestation for each of them
4. Publish the artifact along their attestations

It is not recommended to generate attestations by hand, this process is 
performed by the [pypi-attestation-models] package and needs to be installed.

### Configure the environment

```shell
# Generate a Python environment
python -m venv env-attestations
# Activate it
source env-attestations/bin/activate
# Install dependencies
python -m pip install pypi-attestation-models \ # For generating Attestations
        twine \ # For uploading packages
        sigstore  # For generating the signatures and the OIDC tokens
```

### List every artifact

```python
from pathlib import Path

packages_dir = Path(".").absolute()
dists = [sdist.absolute() for sdist in packages_dir.glob('*.tar.gz')]
dists.extend(whl.absolute() for whl in packages_dir.glob('*.whl'))

# Check that we found some artifacts
assert len(dists) > 1, "Missing artifacts"
```

### Generate an attestation

First, we need to generate a signing token.

```python
from sigstore.oidc import Issuer

issuer = Issuer.production()

# Generates a Token using an OAuth-2 flow
# Warning: Opens a browser
oidc_token = issuer.identity_token()
assert oidc_token is not None, "Failure in generating the token"
```

Then, use this token

```python
from pathlib import Path
from pypi_attestation_models import Attestation

from sigstore.sign import SigningContext, Signer


def attest_dist(package: Path, signer: Signer):
    """Generates an PEP 740 Attestation for a package."""
    attestation_path = Path(f'{package}.publish.attestation')
    attestation = Attestation.sign(signer, package)
    attestation_path.write_text(attestation.model_dump_json(), encoding='utf-8')

signer: Signer = SigningContext.production().signer(identity_token=oidc_token)
for dist in dists:
    attest_dist(dist, signer)
```

### Upload the artifacts generated

Finally, with the generated attestations, it is straightforward to upload 
the packages along their attestations to PyPI (or Test PyPI) using `twine`.

<!-- TODO(dm): Find a solution to pass the OIDC token for the upload. -->

```shell
twine upload -i __token__ dist/* --attestations
```

[Trusted Publishers]: /trusted-publishers/
[pypi-attestation-models]: https://github.com/trailofbits/pypi-attestation-models
