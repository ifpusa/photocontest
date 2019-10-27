import os
from datetime import datetime
from io import BytesIO

import pandas as pd
import sqlalchemy as sa
from flask import Flask, flash, g, jsonify, redirect, render_template, request
from flask.views import MethodView
from marshmallow import fields, post_load
from marshmallow_sqlalchemy import ModelSchema
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from werkzeug.utils import secure_filename

# ┌─────────────────────────────────┐
# │        Database Creation        │
# │                &                │
# │        ORM Mapping stuff        │
# └─────────────────────────────────┘

engine = create_engine("sqlite:///halloween.db", echo=True)
Session = sessionmaker(bind=engine)

Base = declarative_base()


class Submission(Base):

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    contestant = Column(String)
    costume_title = Column(String)
    photo_path = Column(String)
    votes = relationship("Vote")


class Vote(Base):

    __tablename__ = "votes"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime)
    voted_for = Column(Integer, ForeignKey("submissions.id"))


# ┌─────────────────────────────────┐
# │      Object Transformation      │
# │                &                │
# │         Deserialization         │
# └─────────────────────────────────┘


class FieldCountOfVotes(fields.Field):
    """Returns the length of a list of Votes"""

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
            result = g.session.query(Submission).filter_by(id=submission_id).one()
            return jsonify(schema.dump(result))
        except:
            return jsonify(message="That submission doesn't exist!")

    def delete(self, submission_id):

        this_submission = g.session.query(Submission).filter_by(id=submission_id).one()

        try:
            g.session.delete(this_submission)
            g.session.commit()
            return jsonify(message="Delete succesful")
        except:
            return jsonify(message="Could not delete!")


class SubmissionListResource(MethodView):
    def get(self):

        schema = SubmissionSchema(many=True)
        results = g.session.query(Submission).order_by(Submission.contestant).all()

        return jsonify(schema.dump(results))

    def post(self):

        schema = SubmissionSchema()
        this_submission = schema.load(request.json)

        g.session.add(this_submission)
        g.session.commit()

        return jsonify(schema.dump(this_submission))


class VoteResource(MethodView):
    def post(self, submission_id):

        this_vote = Vote(voted_for=submission_id, created_at=datetime.now())
        g.session.add(this_vote)

        try:
            g.session.commit()
            return jsonify(message="success")
        except:
            g.session.close()
            return jsonify(message="failure")


# ┌─────────────────────────────────┐
# │                                 │
# │     Frontend View Functions     │
# │                                 │
# └─────────────────────────────────┘


class PageSubmitAContestant(MethodView):
    def get(self):

        t = sa.text(
            "select b.contestant, count(*) votes \
            FROM votes a \
            JOIN submissions b on a.voted_for = b.id \
            group by b.contestant order by count(*) desc"
        )
        df = pd.read_sql(t, engine)

        return render_template("index.html", standings=df)

    def post(self):
        """Taken straight from Flask docs"""

        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["file"]
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)
        if file and self.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        this_submission = Submission()
        this_submission.contestant = request.form["contestant"]
        this_submission.costume_title = request.form["costume_title"]
        this_submission.photo_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        g.session.add(this_submission)
        g.session.commit()

        return self.get()

    @staticmethod
    def allowed_file(filename):
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
        )


def election_page():

    if datetime.now() > app.config["CONTEST_FINISH_TIME"]:
        closed = True
    else:
        closed = False

    submissions = g.session.query(Submission).order_by(Submission.contestant).all()

    # handle row calculation logic because it's easier to debug here than in Jinja
    submission_count = len(submissions)

    if submission_count % 3 == 0:
        row_count = submission_count // 3
    else:
        row_count = (submission_count // 3) + 1

    grid = []

    for rownum in range(row_count):

        l = []
        if rownum + 1 == row_count:
            row_width = submission_count % 3
        else:
            row_width = 3

        for i in range(row_width):
            l.append(submissions[rownum * 3 + i - 1])

        grid.append(l)

    return render_template("election.html", grid=grid, closed=closed)


# ┌─────────────────────────────────┐
# │       Application Startup       │
# │                &                │
# │              Setup              │
# └─────────────────────────────────┘

# Generate the database
# Does nothing if the database already exists
Base.metadata.create_all(engine, checkfirst=True)


UPLOAD_FOLDER = "static/pics"
ALLOWED_EXTENSIONS = {"jpg"}
CONTEST_FINISH_TIME = datetime.strptime("2019-10-31 14:00", "%Y-%m-%d %H:%M")

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SECRET_KEY"] = "BOO"
app.config["CONTEST_FINISH_TIME"] = CONTEST_FINISH_TIME


@app.before_request
def before_request():
    g.session = Session()


@app.after_request
def after_request(resp):
    g.session.close()
    return resp


app.add_url_rule("/", endpoint="index", view_func=election_page)
app.add_url_rule(
    "/admin",
    endpoint="admin",
    view_func=PageSubmitAContestant.as_view("make_a_submission"),
)

app.add_url_rule(
    "/submissions", view_func=SubmissionListResource.as_view("submissions")
)
app.add_url_rule(
    "/submissions/<submission_id>", view_func=SubmissionResource.as_view("submission")
)
app.add_url_rule("/vote/<submission_id>", view_func=VoteResource.as_view("votes"))
