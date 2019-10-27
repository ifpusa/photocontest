import os
from datetime import datetime
from io import BytesIO


from flask import Flask, request, jsonify, render_template, flash, redirect
from flask.views import MethodView
from werkzeug.utils import secure_filename

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from marshmallow import fields, post_load
from marshmallow_sqlalchemy import ModelSchema

# ┌─────────────────────────────────┐
# │        Database Creation        │
# │                &                │
# │        ORM Mapping stuff        │
# └─────────────────────────────────┘

engine = create_engine('sqlite:///halloween.db', echo=True)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()


class Submission(Base):

	__tablename__ = 'submissions'

	id = Column(Integer, primary_key=True)
	contestant = Column(String)
	costume_title = Column(String)
	photo_path = Column(String)
	votes = relationship("Vote")


class Vote(Base):

	__tablename__ = 'votes'

	id = Column(Integer, primary_key=True)
	created_at = Column(DateTime)
	voted_for = Column(Integer, ForeignKey('submissions.id'))


# ┌─────────────────────────────────┐
# │      Object Transformation      │
# │                &                │
# │         Deserialization         │
# └─────────────────────────────────┘


class FieldCountOfVotes(fields.Field):
	'''Returns the length of a list of Votes'''

	def _serialize(self, value, attr, obj, **kwargs):

		return len(value)

class SubmissionSchema(ModelSchema):
	votes = FieldCountOfVotes(attribute="votes")

	class Meta:
		model = Submission
		transient = True


# ┌─────────────────────────────────┐
# │     API Endpoint Definition     │
# │                &                │
# │         Route Handling          │
# └─────────────────────────────────┘


class SubmissionResource(MethodView):

	def get(self, submission_id):

		schema = SubmissionSchema()

		try:
			result = session.query(Submission).filter_by(id=submission_id).one()
			return jsonify(schema.dump(result))
		except:
			return jsonify(message="That submission doesn't exist!")

	def delete(self, submission_id):

		this_submission = session.query(Submission).filter_by(id=submission_id).one()

		try:
			session.delete(this_submission)
			session.commit()
			return jsonify(message="Delete succesful")
		except:
			return jsonify(message="Could not delete!")


class SubmissionListResource(MethodView):

	def get(self):

		schema = SubmissionSchema(many=True)
		results = session.query(Submission).all()

		return jsonify(schema.dump(results))


	def post(self):

		schema = SubmissionSchema()
		this_submission = schema.load(request.json)

		session.add(this_submission)
		session.commit()

		return jsonify(schema.dump(this_submission))

class VoteResource(MethodView):

	def post(self, submission_id):

		this_vote = Vote(voted_for=submission_id, created_at=datetime.now())
		session.add(this_vote)
		try:
			session.commit()
			return jsonify(message="success")
		except:
			return jsonify(message="failure")


# ┌─────────────────────────────────┐
# │                                 │
# │     Frontend View Functions     │
# │                                 │
# └─────────────────────────────────┘

def create_submission():
	'''Taken straight from Flask docs'''

	if request.method == 'POST':
			# check if the post request has the file part
			if 'file' not in request.files:
				flash('No file part')
				return redirect(request.url)
			file = request.files['file']
			# if user does not select file, browser also
			# submit an empty part without filename
			if file.filename == '':
				flash('No selected file')
				return redirect(request.url)
			if file and allowed_file(file.filename):
				filename = secure_filename(file.filename)
				file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
				
			this_submission = Submission()
			this_submission.contestant=request.form['contestant']
			this_submission.costume_title=request.form['costume_title']
			this_submission.photo_path=os.path.join(app.config['UPLOAD_FOLDER'], filename)

			session.add(this_submission)
			session.commit()
	else:
		return render_template('index.html')
	


# ┌─────────────────────────────────┐
# │       Application Startup       │
# │                &                │
# │              Setup              │
# └─────────────────────────────────┘

# Generate the database
# Does nothing if the database already exists
Base.metadata.create_all(engine, checkfirst=True)

UPLOAD_FOLDER = 'static/pics'
ALLOWED_EXTENSIONS = {'jpg'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'BOO'

app.add_url_rule('/add', endpoint='add', view_func=create_submission, methods=["GET", "POST"])

app.add_url_rule('/submissions', view_func=SubmissionListResource.as_view('submissions'))
app.add_url_rule('/submissions/<submission_id>', view_func=SubmissionResource.as_view('submission'))
app.add_url_rule('/vote/<submission_id>', view_func=VoteResource.as_view('votes'))




def allowed_file(filename):
	return '.' in filename and \
		   filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

