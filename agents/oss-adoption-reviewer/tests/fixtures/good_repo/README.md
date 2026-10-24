# Goodapp

A tiny CLI that greets people by name, with colour and in any language.

## Why

Greeting scripts are copy-pasted between projects and drift apart. Goodapp keeps one tested implementation.

## Prerequisites

- Python 3.12+
- uv

## Installation

```bash
uv sync
cp .env.example .env
```

## Usage

```bash
uv run python app.py World
```

## Example output

```
Hello, World!
```

## Configuration

Set `GREETING` in `.env` to change the salutation. Every other behaviour is controlled by command-line flags, so the tool needs no config file.
