# wikidata-rdf-patch

Edit Wikidata items with RDF. Kinda like [QuickStatements](https://quickstatements.toolforge.org/#/), but more powerful.

## Installation

Install this tool using `pip`:

```sh
$ pip install git+https://github.com/josh/wikidata-rdf-patch.git
```

## Usage

For help, run:

```sh
$ wikidata-rdf-patch --help
```

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

```sh
$ cd wikidata-rdf-patch/
$ uv venv
$ source .venv/bin/activate
```

Now install the dependencies and test dependencies:

```bash
$ pip install -e '.[test]'
```

To run the tests:

```sh
$ pytest
```
