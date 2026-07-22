# Community Complaint System - Project Report

## 1. Project Title

**Community Complaint System**

The project is also presented in the user interface as **CivicConnect**, a web-based platform for reporting and managing civic grievances.

## 2. Abstract

The Community Complaint System is a web-based grievance management application developed using Python Flask and SQLite. The system provides a centralized platform where citizens can register, log in, submit civic complaints, upload supporting images, track complaint progress, communicate through complaint-specific discussion threads, and provide feedback after resolution.

The application also provides an administrator panel for municipal staff. Administrators can view all registered complaints, filter and search complaint records, assign departments, update complaint status, upload resolution proof images, monitor lifecycle history, and analyze dashboard metrics such as total complaints, active complaints, resolved issues, average resolution time, and citizen satisfaction rating.

The main purpose of the project is to improve transparency, accountability, and efficiency in public complaint handling. It replaces informal and manual complaint tracking with a structured digital workflow that benefits both citizens and authorities.

## 3. Introduction

Public infrastructure problems such as potholes, garbage overflow, streetlight failure, water shortage, damaged park equipment, and public safety issues are common in communities. In many cases, citizens do not have a transparent way to report such issues or track whether action has been taken. Traditional methods such as phone calls, written applications, or direct office visits may cause delays, duplicate complaints, poor record keeping, and lack of accountability.

The Community Complaint System addresses this problem by providing an online portal for citizens and administrators. Citizens can report issues with details and photographs, while administrators can manage complaints through a clear workflow. Each complaint maintains a timeline of updates, making the entire process more transparent and easier to monitor.

## 4. Problem Statement

In many local communities, complaint registration and resolution are handled manually or through disconnected communication channels. This creates several problems:

- Citizens cannot easily track the progress of their complaints.
- Authorities may find it difficult to prioritize and assign complaints.
- Complaint records may be lost, duplicated, or delayed.
- There is limited proof that a complaint has actually been resolved.
- Feedback from citizens is often not collected after resolution.
- Municipal staff may not have analytical data for decision-making.

Therefore, there is a need for a centralized web-based complaint management system that allows citizens to submit complaints and allows administrators to track, assign, resolve, and analyze those complaints efficiently.

## 5. Objectives

The main objectives of the project are:

- To develop an online platform for citizen complaint registration.
- To provide secure login and role-based access for citizens and administrators.
- To allow citizens to submit complaint details such as title, category, location, description, and supporting image.
- To allow citizens to view the current status and timeline of their submitted complaints.
- To provide an admin dashboard for monitoring and managing all complaints.
- To allow administrators to assign complaints to responsible departments.
- To maintain status history for every complaint.
- To require resolution proof image upload before marking a complaint as resolved.
- To collect feedback and ratings from citizens after complaint resolution.
- To generate useful administrative statistics and charts.

## 6. Scope of the Project

The scope of the project includes the design and implementation of a complete basic complaint management workflow.

### Included Scope

- Citizen registration and login.
- Citizen dashboard for submitted complaints.
- Complaint filing with category, location, description, and optional image.
- Admin dashboard for viewing and managing all complaints.
- Search and filtering by complaint status, category, department, and keyword.
- Status lifecycle management.
- Department assignment.
- Complaint detail view.
- Timeline and discussion comments.
- Resolution proof upload.
- Citizen feedback and rating.
- Dashboard analytics using charts.
- SQLite-based data storage.
- Basic deployment support using Gunicorn, Procfile, and Render configuration.

### Out of Scope for Current Version

- Mobile application.
- SMS/email notifications.
- GPS/map-based complaint location.
- Multiple department staff roles.
- Online payment or penalty management.
- AI-based automatic classification.
- Large-scale production database clustering.

## 7. Background Study

Complaint management systems are important tools in public administration and service delivery. A good grievance system should allow users to submit issues easily, should give administrators a structured way to process those issues, and should provide transparency throughout the process.

Manual systems often depend on paper records, phone calls, or office visits. These systems can work on a small scale but become inefficient when complaint volume increases. Digital complaint systems solve this by storing all data in a database, providing role-based dashboards, allowing real-time status tracking, and generating reports for decision-making.

This project follows the basic principles of e-governance systems:

- Accessibility for citizens.
- Accountability for administrators.
- Transparency in status updates.
- Evidence-based complaint reporting.
- Feedback-based service improvement.

## 8. Technology Stack

| Layer | Technology Used | Purpose |
| --- | --- | --- |
| Frontend | HTML, CSS, JavaScript | User interface and client-side interaction |
| Template Engine | Jinja2 | Dynamic rendering of HTML pages |
| Backend | Python Flask | Web application routing and server-side logic |
| Database | SQLite | Local relational database storage |
| Authentication | Flask session, Werkzeug security | Login sessions and password hashing |
| File Handling | Werkzeug secure filename, local uploads | Safe image upload and storage |
| Charts | Chart.js | Admin dashboard visual analytics |
| Server | Gunicorn | Production WSGI server |
| Deployment Config | Procfile, render.yaml | Cloud deployment support |

## 9. System Users

### Citizen

The citizen is the primary public user of the system. A citizen can:

- Register an account.
- Log in and log out.
- File a new complaint.
- Upload an optional issue image.
- View personal complaint history.
- Open complaint details.
- Add comments to the complaint discussion.
- View status updates.
- Submit feedback after resolution.

### Administrator

The administrator manages complaints and monitors system activity. An administrator can:

- Log in to the admin dashboard.
- View all submitted complaints.
- Search and filter complaint records.
- Assign a complaint to a department.
- Update complaint status.
- Upload resolution proof image.
- Add official update notes.
- View registered users.
- View analytical charts and metrics.

## 10. Functional Requirements

- The system must allow citizens to register with username, full name, email, phone, and password.
- The system must allow users to log in using username and password.
- The system must distinguish between citizen and admin roles.
- The system must allow citizens to submit complaints.
- The system must validate required complaint fields.
- The system must allow optional image upload for complaint evidence.
- The system must allow citizens to see only their own complaints.
- The system must allow administrators to view all complaints.
- The system must allow administrators to filter complaints.
- The system must allow administrators to assign departments.
- The system must allow administrators to update complaint status.
- The system must require a resolution proof image when marking a complaint as resolved.
- The system must maintain a timeline of status updates and comments.
- The system must allow feedback only after a complaint is resolved.
- The system must calculate dashboard statistics.

## 11. Non-Functional Requirements

- The system should be easy to use.
- The system should protect user passwords using hashing.
- The system should restrict access based on user role.
- The system should store data consistently in a relational database.
- The system should validate uploaded file extensions.
- The system should support a maximum upload size of 5 MB.
- The system should be simple to deploy.
- The system should provide clear visual feedback using messages and badges.
- The system should be maintainable with separated application and database logic.

## 12. Data Used

The project uses structured data stored in an SQLite database. The application can also seed demonstration data using `seed.py`.

### Main Data Entities

| Entity | Description |
| --- | --- |
| User data | Stores citizen and admin account details |
| Complaint data | Stores title, category, location, description, status, department, and image paths |
| Complaint update data | Stores timeline history, status changes, comments, and author information |
| Feedback data | Stores citizen rating and feedback comments |
| Image data | Stores uploaded complaint images and resolution proof image filenames |

### Demo Data

The seed file creates sample users and complaints, including:

- Admin account.
- Citizen accounts.
- Pothole complaint.
- Garbage overflow complaint.
- Broken streetlight complaint.
- Low water pressure complaint.
- Broken park swing complaint.
- Sample complaint updates.
- Sample feedback ratings.
- Mock image files for issue and resolution proof.

## 13. Database Design

The database is defined in `schema.sql` and contains four main tables.

### `users`

Stores account information for citizens and administrators.

Important fields:

- `id`
- `username`
- `password_hash`
- `full_name`
- `email`
- `phone`
- `role`
- `created_at`

### `complaints`

Stores core complaint records.

Important fields:

- `id`
- `citizen_id`
- `title`
- `category`
- `description`
- `location`
- `image_path`
- `status`
- `department`
- `resolution_image_path`
- `created_at`
- `updated_at`

### `complaint_updates`

Stores status changes, comments, and official notes.

Important fields:

- `id`
- `complaint_id`
- `author_id`
- `status_from`
- `status_to`
- `message`
- `created_at`

### `feedback`

Stores feedback submitted by citizens after resolution.

Important fields:

- `id`
- `complaint_id`
- `rating`
- `comments`
- `created_at`

## 14. System Architecture

The project follows a three-layer web application architecture.

### Presentation Layer

This layer contains the user interface.

Files:

- `templates/index.html`
- `templates/register.html`
- `templates/login.html`
- `templates/citizen_dashboard.html`
- `templates/file_complaint.html`
- `templates/admin_dashboard.html`
- `templates/complaint_detail.html`
- `templates/base.html`
- `static/css/style.css`
- `static/js/main.js`
- `static/js/admin.js`

### Application Layer

This layer contains the Flask application logic.

Main file:

- `app.py`

Responsibilities:

- Route handling.
- Authentication.
- Session management.
- Role checking.
- Form processing.
- File upload handling.
- Complaint workflow control.
- Feedback submission.
- API response for dashboard stats.

### Data Layer

This layer handles database operations.

Main files:

- `database.py`
- `schema.sql`

Responsibilities:

- Database connection.
- User creation and lookup.
- Complaint creation.
- Complaint retrieval.
- Status updates.
- Department assignment.
- Comment insertion.
- Feedback insertion.
- Dashboard statistics calculation.

## 15. Complaint Workflow

The complaint lifecycle follows these steps:

1. Citizen registers or logs into the system.
2. Citizen files a complaint with required details.
3. The system stores the complaint with `Pending` status.
4. Administrator reviews the complaint.
5. Administrator may assign the complaint to a department.
6. Administrator changes status to `Under Review` or `In Progress`.
7. Administrator uploads proof and marks the complaint as `Resolved`.
8. Citizen views the resolution details.
9. Citizen submits rating and feedback.

Supported statuses:

- `Pending`
- `Under Review`
- `In Progress`
- `Resolved`
- `Rejected`

## 16. Main Features

### Citizen Features

- Account registration.
- Login and logout.
- Complaint submission.
- Image upload.
- Personal dashboard.
- Complaint detail page.
- Timeline tracking.
- Comment posting.
- Feedback after resolution.

### Admin Features

- Admin dashboard.
- Complaint register.
- User register.
- Complaint filtering.
- Complaint search.
- Department assignment.
- Status update.
- Official notes.
- Mandatory resolution proof.
- Dashboard charts.
- Average resolution time calculation.
- Average satisfaction rating calculation.

## 17. Route Design

| Route | Method | Access | Description |
| --- | --- | --- | --- |
| `/` | GET | Public | Home page |
| `/register` | GET/POST | Public | Citizen registration |
| `/login` | GET/POST | Public | User login |
| `/logout` | GET | Logged-in users | Logout |
| `/dashboard` | GET | Citizen | Citizen complaint dashboard |
| `/file-complaint` | GET/POST | Citizen | Submit complaint |
| `/complaint/<id>` | GET | Logged-in users | Complaint detail page |
| `/complaint/<id>/comment` | POST | Logged-in users | Add discussion comment |
| `/admin/dashboard` | GET | Admin | Admin dashboard |
| `/complaint/<id>/action` | POST | Admin | Update status or department |
| `/complaint/<id>/feedback` | POST | Citizen | Submit feedback |
| `/api/admin/stats` | GET | Admin | Return dashboard stats as JSON |
| `/static/uploads/<filename>` | GET | Public | Serve uploaded images |

## 18. Security and Validation

The project includes several basic security measures:

- Passwords are stored as hashes using Werkzeug.
- User sessions are used for login state.
- Role-based decorators protect restricted pages.
- Citizens cannot access complaints submitted by other citizens.
- Admin-only routes require admin role.
- Uploaded filenames are sanitized using `secure_filename`.
- Uploaded files are renamed with UUID prefixes to avoid filename collisions.
- Only selected image extensions are allowed.
- File upload size is limited to 5 MB.
- SQL queries use parameterized statements.
- SQLite foreign keys are enabled.

Current security improvement needed:

- CSRF protection should be added before production deployment.
- Strong secret key should be configured using environment variables.
- Production deployment should use HTTPS.

## 19. Admin Analytics

The admin dashboard calculates and displays useful complaint statistics:

- Total number of complaints.
- Number of unresolved active complaints.
- Number of resolved complaints.
- Average resolution time.
- Average citizen feedback rating.
- Complaints grouped by category.
- Complaints grouped by status.
- Complaints grouped by department.

Charts are rendered using Chart.js, and the backend provides JSON statistics through `/api/admin/stats`.

## 20. Project File Structure

```text
community-complaint-system-master/
|-- app.py
|-- database.py
|-- schema.sql
|-- seed.py
|-- requirements.txt
|-- Procfile
|-- render.yaml
|-- PROJECT_REPORT.md
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- register.html
|   |-- login.html
|   |-- citizen_dashboard.html
|   |-- file_complaint.html
|   |-- admin_dashboard.html
|   |-- complaint_detail.html
|-- static/
|   |-- css/
|   |   |-- style.css
|   |-- js/
|   |   |-- main.js
|   |   |-- admin.js
```

## 21. Implementation Details

### Authentication

The application uses Flask sessions to store logged-in user details such as user ID, username, full name, and role. Passwords are verified using Werkzeug password hashing functions.

### Authorization

Two helper decorators are used:

- `login_required`
- `role_required`

These decorators ensure that protected pages can only be accessed by authorized users.

### File Upload

The complaint image and resolution proof image are saved in the configured upload folder. The system checks file extensions and uses a UUID prefix for uniqueness.

Allowed formats:

- PNG
- JPG
- JPEG
- GIF

### Complaint History

Every complaint status change or comment is stored in the `complaint_updates` table. This creates a timeline that both citizens and administrators can view.

### Feedback

Feedback is only allowed when a complaint has been resolved. Each complaint can have only one feedback record because `complaint_id` is unique in the feedback table.

## 22. Testing Approach

The following manual testing scenarios can be used:

| Test Case | Expected Result |
| --- | --- |
| Register a new citizen | User account is created |
| Login with valid credentials | User is redirected to correct dashboard |
| Login with invalid credentials | Error message is shown |
| Submit complaint with required fields | Complaint is stored with Pending status |
| Submit complaint without required fields | Validation message is shown |
| Upload invalid file type | Upload is rejected |
| Citizen opens another user's complaint | Access is denied |
| Admin updates status | Status and timeline are updated |
| Admin resolves without proof image | Resolution is rejected |
| Admin resolves with proof image | Complaint is marked Resolved |
| Citizen submits feedback | Feedback is saved |
| Admin applies filters | Complaint list is filtered |
| Dashboard chart loads | Chart data is displayed |

## 23. Limitations

- The project currently uses SQLite, which is best for small and medium prototypes.
- No CSRF protection is implemented yet.
- Email and SMS notifications are not available.
- There is no map-based location picker.
- There is no separate department staff dashboard.
- Uploaded files are stored locally.
- There is no automated test suite.
- The admin account is created through seed data rather than a dedicated admin creation panel.

## 24. Future Enhancements

The project can be improved in the following ways:

- Add CSRF protection using Flask-WTF.
- Add email and SMS notifications for complaint updates.
- Add map-based location selection using Google Maps or OpenStreetMap.
- Add separate department staff accounts.
- Add priority levels such as low, medium, high, and urgent.
- Add complaint escalation when resolution is delayed.
- Add PDF and Excel report export.
- Add mobile application support.
- Add REST API for external integration.
- Replace SQLite with PostgreSQL or MySQL for production.
- Store uploaded images in cloud storage.
- Add automated tests using pytest.
- Add AI-based category prediction from complaint description.
- Add multilingual support for citizens.
- Add complaint reopening if the citizen is not satisfied.

## 25. Conclusion

The Community Complaint System successfully provides a digital platform for registering, managing, tracking, and resolving civic complaints. It improves communication between citizens and administrators by offering structured complaint submission, timeline updates, department assignment, proof-based resolution, and feedback collection.

The project demonstrates practical use of Flask, SQLite, authentication, role-based access control, file uploads, database design, and dashboard analytics. Although the current version is suitable as a strong academic or prototype project, it can be extended into a production-ready e-governance system with stronger security, notification services, scalable database support, and mobile accessibility.

