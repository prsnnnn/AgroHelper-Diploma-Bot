# 🌾 AgroManager

> **Student:** Serediuk Yehor
> **Group:** 121-22-3

---

## Content

* [Goal of work](#goal of work)
* [Technology Stack](#technology-stack)
* [Architecture](#architecture)
* [Database](#database)
* [Functional](#functional)
* [Project structure](#project-structure)
* [Results](#results)
* [Conclusions](#conclusions)

---

## Work goal
Develop a full-fledged client-server application in the Java language that implements the business logic of agricultural resource management (AgroTech). The project combines work with a database, REST API and integration with external services.

## Technological stack
* **Backend:** Java 17, Spring Boot 3.x
* **Database:** H2 Database (In-memory)
* **ORM:** Spring Data JPA (Hibernate)
* **Frontend:** Thymeleaf (Server-side rendering)
* **API Parsing:** RestTemplate (JSON processing)

## Architecture
### Application layers
* **Controller:** HTTP request processing and routing.
* **Service:** Business logic and interaction with external API.
* **Repository:** Interaction with the database via JPA.
* **Model:** Description of entities (Entities).

## Database
A relational model with a **One-to-Many** connection is used:
* **Table `farms`:** name, latitude, longitude.
* **Table `sensors`:** sensor type, activity status, farm id.

## Functionality
* ✅ **CRUD operations:** Complete management of farm and sensor data.
* 🔍 **Monitoring:** Viewing the status of objects in real time.
* 🌐 **External API parsing:** Automatic weather retrieval via Open-Meteo.
* 🎭 **DTO pattern:** Using Records for secure data transfer.

## Project structure
The project is organized according to the package principle:
- `controller/` — request processing.
- `service/` — logic and parsing.
- `repository/` — access to the database.
- `model/` — database entities.

## Results
The application successfully integrates data from the database and external API, displaying the current temperature for selected locations (Ulsteinvik, Kyiv) on the front-end panel.
<img width="1810" height="345" alt="image" src="https://github.com/user-attachments/assets/c3d8a723-1336-4462-8eb2-9db2858f760e" />
<img width="1606" height="125" alt="image" src="https://github.com/user-attachments/assets/9e6104da-1660-43a9-9f81-27a856c55059" />
<img width="577" height="508" alt="image" src="https://github.com/user-attachments/assets/8d793b30-bf49-436d-b6b5-7776f198da69" />
