FROM python:3.12-slim
WORKDIR /app
COPY incident_lab /app/incident_lab
COPY LICENSE /app/LICENSE
RUN mkdir /app/artifacts && chown 65532:65532 /app/artifacts
USER 65532:65532
ENTRYPOINT ["python", "-m", "incident_lab"]
CMD ["demo", "--scenario", "INC-001"]
