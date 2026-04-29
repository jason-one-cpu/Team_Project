# E-Scooter Hiring Application

## Project Overview

This project is an e-scooter hiring application for use in the city centre. The system is intended to support both customers and managers.

Customer-side features include:

- account registration and login
- booking an e-scooter
- viewing scooter locations
- viewing booking history, duration, and cost
- reporting issues or faults

Manager-side features include:

- reviewing customer and booking data
- handling reported faults
- configuring prices and discounts
- viewing revenue-related information

## Team Members

### Sun Zixuan (Team Leader)

Role: Backend Developer and Project Coordinator  
Belbin Type: Chair (CH) and Company Worker (CW)  
Responsibilities: Managing the repository structure, coordinating sprint tasks, supporting backend planning, and helping turn team decisions into practical work items.

### webb

Role: Technical Research and Design Support  
Belbin Type: Plant (PL) and Resource Investigator (RI)  
Responsibilities: Exploring technical options, contributing creative ideas for the e-scooter system, supporting architecture and design discussion, and researching suitable tools or frameworks.

### sfd23

Role: Documentation and Quality Support  
Belbin Type: Team Worker (TW) and Completer/Finisher (CF)  
Responsibilities: Supporting team communication, maintaining documentation quality, checking sprint records for completeness, and helping ensure that tasks and materials are finished carefully.

## Sprint 1 Focus

Sprint 1 was used as a preparation stage. The main goals were to establish the project environment, agree the initial design direction, and prepare the team for implementation work in later sprints.

This included:

- setting up the repository structure
- creating initial GitHub issues and wiki records
- documenting team roles and responsibilities
- discussing the initial architecture
- identifying the first backlog items for implementation

## Proposed Repository Structure

```text
Team_Project/
|-- README.md
|-- backend/
|   |-- __init__.py
|   `-- server.py
|-- frontend/
|   |-- index.html
|   |-- styles.css
|   `-- main.js
|-- tests/
`-- .gitignore
```

## Initial Technical Direction

The team plans to build a client-server application for e-scooter hiring. At this stage, the exact framework and database can still be adjusted after further discussion and evaluation.

The system is expected to include:

- a customer-facing interface
- a management-facing interface
- server-side booking and issue-handling logic
- persistent storage for users, scooters, bookings, and pricing data

## Team Workflow

- Project tasks are tracked using GitHub Issues.
- Sprint work is organised through milestones and labels.
- Design notes, sprint plans, outcomes, and meeting records are documented in the project wiki and repository docs.
- Team members discuss progress in regular sprint meetings and record decisions clearly.

## Current Status

This repository now contains the completed Sprint 4 project version.

The current system includes:

- a SQLite-backed backend in `backend/server.py`
- customer registration and login
- secure password handling with hashed storage
- map-based store and scooter browsing
- simulated card payment and saved card reuse
- booking confirmation records and email logs
- booking history with route tracking
- issue reporting and high-priority issue handling
- manager tools for stores, scooters, users, issues, and statistics
- automated backend tests in `tests/test_server.py`

## Requirements

- Python 3.11 or newer is recommended
- no third-party packages are required
- SQLite is used through Python's standard library

## Project Commands

### Start the project

Open the project folder in PowerShell and run:

```powershell
python backend/server.py
```

This starts the local backend and serves the frontend at:

```text
http://127.0.0.1:8000
```

### Run tests

```powershell
python -m unittest discover -s tests -v
```

## Supporting Documentation

The project also includes supporting documentation in the `docs` folder for:

- sprint planning and outcomes
- task allocation
- meeting records
- final backlog checklist
- data modelling
- testing process and evidence
- user manual
- team reflection notes
