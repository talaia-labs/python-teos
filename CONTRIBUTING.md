# Contributing to PISA

The following is a set of guidelines for contributing to PISA.

## Code Style Guidelines
We use [black](https://github.com/psf/black) as our base code formatter. Before submitting a PR make sure you have properly formatted your code by running:

```
black {source_file_or_directory}
```
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

## Code Documentation
Code should be, at least, documented using docstrings. We use the [Sphinx Google Style](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html#example-google) for documenting functions.

## Test Coverage
Tests should be provided to cover both positive and negative conditions. Test should cover both the proper execution as well as all the covered error paths. PR with no proper test coverage will be rejected. 


