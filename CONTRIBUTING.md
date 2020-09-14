# Contributing to the Eye of Satoshi

The following is a set of guidelines for contributing to TEOS.

## Code Style Guidelines
We use [black](https://github.com/psf/black) as our base code formatter with a line length of 120 chars. Before submitting a PR make sure you have properly formatted your code by running:

```bash
black --line-length=120 {source_file_or_directory}
```

In additon, we use [flake8](https://flake8.pycqa.org/en/latest/) to detect style issues with the code:

```bash
flake8 --max-line-length=120 {source_file_or_directory}
```

 Not all outputs from flake8 are mandatory. For instance, splitting **bullet points in docstrings (E501)** will cause issues when generating the documentation, so we will leave that longer than the line length limit . Another example are **whitespaces before colons in inline fors (E203)**. `black` places them in that way, so we'll leave them like that.

On top of that, there are a few rules to also have in mind.

### Code Spacing
Blocks of code should be created to separate logical sections

```python
responder = Responder(db_manager)
responder.jobs, responder.tx_job_map = Builder.build_jobs(responder_jobs_data)

watcher.responder = responder
watcher.appointments, watcher.locator_uuid_map = Builder.build_appointments(watcher_appointments_data)
```
We favour spacing between blocks like `if/else`, `try/except`, etc.

```python
if tx in missed_confirmations:
    missed_confirmations[tx] += 1

else:
    missed_confirmations[tx] = 1
```

An exception to the rule are nested `if` statements that placed right after each other and `if` statements with a single line of code.

```python
for opt, arg in opts:
    if opt in ["-s", "server"]:
        if arg:
            teos_api_server = arg
```

```python
if appointment_data is None:
    raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty appointment received")
elif not isinstance(appointment_data, dict):
    raise InspectionFailed(errors.APPOINTMENT_WRONG_FIELD, "wrong appointment format")
```

## Dev Requirements
In order to contrubite you will need to install additional dependencies. They can be found at `requirements-dev.txt`. Install them by running:

	pip install -r requirements-dev.txt

## Code Documentation
Code should be, at least, documented using docstrings. We use the [Sphinx Google Style](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html#example-google) for documenting functions.

Here's an example of method docs:

```
"""
Manages the add_appointment command. The life cycle of the function is as follows:
    - Sign the appointment
    - Send the appointment to the tower
    - Wait for the response
    - Check the tower's response and signature

Args:
    appointment (:obj:`Appointment <common.appointment.Appointment>`): an appointment object.
    user_sk (:obj:`PrivateKey`): the user's private key.
    teos_id (:obj:`str`): the tower's compressed public key.
    teos_url (:obj:`str`): the teos base url.

Returns:
    :obj:`tuple`: A tuple containing the start block and the tower's signature of the appointment.

Raises:
    :obj:`ValueError`: if the appointment cannot be signed.
    :obj:`ConnectionError`: if the client cannot connect to the tower.
    :obj:`TowerResponseError`: if the tower responded with an error, or the response was invalid.
"""
```

- In `Args`, custom types need to be linked (`Appointment <common.appointment.Appointment>`) to the proper file. 
Same happens within `Return`. `Raises` is special though. Exceptions must not be linked (or it will create a format error).
- Text that wraps around the line limit need to be indented in `Args` and `Raises`, but not in `Return`.
- Only `Returns` and `Attributes` docs are capitalized, not `Args`, nor `Raises`. 
- Variable names can be highlighted using \`\`var_name\`\`. For types, :obj:\`TypeName\` must be used.

      

## Test Coverage
We use [pytest](https://docs.pytest.org/en/latest/) to build and run tests. Tests should be provided to cover both positive and negative conditions. Test should cover both the proper execution as well as all the covered error paths. PR with no proper test coverage will be rejected. 

## Signing Commits

We require that all commits to be merge into master are signed. You can enable commit signing on GitHub by following [Signing commits](https://help.github.com/en/github/authenticating-to-github/signing-commits).

