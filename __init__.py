import os
from datetime import datetime
from io import BytesIO

import pandas as pd
import sqlalchemy as sa
from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    current_app,
)
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

engine = create_engine(f"sqlite:///halloween.db", echo=True)
Session = sessionmaker(bind=engine)

Base = declarative_base()


class Submission(Base):

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    contestant = Column(String)
    costume_title = Column(String)
    photo_path = Column(String)
    votes = relationship("Vote", cascade="all, delete, delete-orphan")


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


class AdminPageView(MethodView):
    def get(self):

        t = sa.text(
            "select a.id, a.contestant, count(b.id) votes \
FROM submissions a LEFT JOIN votes b on a.id = b.voted_for \
GROUP BY a.id, a.contestant ORDER BY count(b.id) DESC"
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
            file.save(os.path.join(ABS_UPLOAD_FOLDER, filename))

        this_submission = Submission()
        this_submission.contestant = request.form["contestant"]
        this_submission.costume_title = request.form["costume_title"]
        this_submission.photo_path = os.path.join(UPLOAD_FOLDER, filename)

        g.session.add(this_submission)
        g.session.commit()

        return self.get()

    @staticmethod
    def allowed_file(filename):
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
        )


def election_page():

    if datetime.now() > CONTEST_FINISH_TIME:
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

    # split the list of grids into groups of three
    grid = [submissions[i : i + 3] for i in range(0, len(submissions), 3)]

    return render_template("election.html", grid=grid, closed=closed)


# ┌─────────────────────────────────┐
# │       Application Startup       │
# │                &                │
# │              Setup              │
# └─────────────────────────────────┘

# Generate the database
# Does nothing if the database already exists
Base.metadata.create_all(engine, checkfirst=True)


bp = Blueprint(
    "photovote", __name__, static_folder="static", template_folder="templates"
)

UPLOAD_FOLDER = "static/pics"
ABS_UPLOAD_FOLDER = os.path.join(*[bp.static_folder, "pics"])
ALLOWED_EXTENSIONS = {"jpg"}
CONTEST_FINISH_TIME = datetime.strptime("2019-10-31 14:00", "%Y-%m-%d %H:%M")

SECRET_KEY = "BOO"
CONTEST_FINISH_TIME = CONTEST_FINISH_TIME


@bp.before_request
def before_request():
    g.session = Session()


@bp.after_request
def after_request(resp):

    g.session.close()
    return resp


bp.add_url_rule("/", endpoint="index", view_func=election_page)
bp.add_url_rule(
    "/admin", endpoint="admin", view_func=AdminPageView.as_view("make_a_submission")
)

bp.add_url_rule("/submissions", view_func=SubmissionListResource.as_view("submissions"))
bp.add_url_rule(
    "/submissions/<submission_id>", view_func=SubmissionResource.as_view("submission")
)
bp.add_url_rule("/vote/<submission_id>", view_func=VoteResource.as_view("votes"))
