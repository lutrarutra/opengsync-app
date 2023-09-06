# import subprocess
# import json

# from flask import Blueprint, request, redirect, url_for, Response

# import flask_wtf

# from ... import models, logger
# # from demux.utils import io_tools

# jobs_bp = Blueprint("jobs_bp", __name__, url_prefix="/api/jobs/")
# api = Api(jobs_bp)


# class ChangeJobStatus(Resource):
#     def post(self):
#         logger.debug(request.form)
#         res = flask_wtf.csrf.validate_csrf(request.form, token_key="csrf_token")
#         logger.debug(res)

#         job_id = request.form.get("job_id")
#         if not job_id:
#             error = json.dumps({"error": "Job ID 'job_id' not found in request body."})
#             return Response(error, status=400)

#         status = request.form.get("status")
#         if not status:
#             error = json.dumps({"error": "Job Status 'status' not found in request body."})
#             return Response(error, status=400)

#         try:
#             status = int(status)
#         except ValueError:
#             error = json.dumps({"error": f"Job Status, '{status}', is not a valid status."})
#             return Response(error, status=400)

#         if not models.JobStatus.is_valid_status(status):
#             error = json.dumps({"error": f"Job Status, '{status}', is not a valid status."})
#             return Response(error, status=400)

#         with SessionLocal() as session:
#             job = session.get(models.Job, job_id)
#             if job:
#                 job.status = status
#                 session.commit()
#             else:
#                 error = json.dumps({"error": f"Job, with id '{job_id}', could not be found."})
#                 return Response(error, status=404)

#         return Response("", status=200)


# class RunJob(Resource):
#     def get(self, job_id):
#         with SessionLocal() as session:
#             job = session.get(models.Job, job_id)

#             if job:
#                 script = io_tools.read_template(
#                     "/home/agynter/documents/tenx_pipeline/demux/templates/testjob.batch"
#                 ).substitute(
#                     host="localhost",  # request.environ.get("SERVER_NAME"),
#                     port=request.environ.get("SERVER_PORT"),
#                     job_id=job.id,
#                     csrf_token=flask_wtf.csrf.generate_csrf()
#                 )
#                 with open("script.sh", "w") as f:
#                     f.write(script)

#                 try:
#                     subprocess.run(["sbatch", "/home/agynter/documents/script.sh"])
#                 except subprocess.CalledProcessError as e:
#                     print(e)

#         return redirect(url_for("index_page"))


# api.add_resource(ChangeJobStatus, "status")
# api.add_resource(RunJob, "run/<int:job_id>")
