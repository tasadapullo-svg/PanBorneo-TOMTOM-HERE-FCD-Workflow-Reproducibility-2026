# Java acquisition notes

The historical development repository used a Java/Spring Boot acquisition service. The relevant source files were reviewed only as code provenance:

- `TomTomCollectorTask.java`: TomTom request loop and response retrieval.
- `HereCollectorTask.java`: HERE request loop, decompression, and response retrieval.
- `TomTomController.java` and `HereController.java`: scheduled polling orchestration.
- `DataTomtomCoordinateImpl.java`: TomTom response parsing.
- `BaseMonitorBboxImpl.java`: HERE response parsing and segment extraction.

The full backend is not copied into this public release because it contains operational infrastructure concerns such as database, scheduler, logging, and credential-loading code. The public release instead provides de-identified Python acquisition templates and this implementation note.
