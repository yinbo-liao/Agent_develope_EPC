"""Training Management router — roles, courses, personnel, certification tracking."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from auth import get_current_user, TokenData
from errors import not_found

router = APIRouter(prefix="/api/training", tags=["training"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---- Pydantic Schemas ----

class RoleCreate(BaseModel):
    role_name: str
    role_category: Optional[str] = None


class CourseCreate(BaseModel):
    course_code: str
    course_name: str
    course_category: Optional[str] = None
    validity_months: Optional[int] = None
    is_mandatory: bool = False
    description: Optional[str] = None


class RoleRequirementCreate(BaseModel):
    role_id: int
    course_id: int


class PersonnelCreate(BaseModel):
    badge_number: str
    full_name: str
    role_id: Optional[int] = None
    discipline: Optional[str] = None
    contractor_company: Optional[str] = None
    mobilization_date: Optional[date] = None


class TrainingRecordCreate(BaseModel):
    personnel_id: str
    course_id: int
    completion_date: date
    expiry_date: Optional[date] = None
    certificate_ref: Optional[str] = None
    score: Optional[float] = None
    verified_by: Optional[str] = None


# ---- Roles ----

@router.get("/roles")
async def list_roles(page: int = 1, page_size: int = 500, db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("SELECT * FROM training_roles ORDER BY role_category, role_name "
             "LIMIT :limit OFFSET :offset"),
        {"limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


@router.post("/roles")
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO training_roles (role_name, role_category) VALUES (:name, :cat) "
             "ON CONFLICT (role_name) DO NOTHING"),
        {"name": data.role_name, "cat": data.role_category}
    )
    await db.commit()
    return {"status": "created"}


# ---- Courses ----

@router.get("/courses")
async def list_courses(page: int = 1, page_size: int = 500, db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("SELECT * FROM training_courses ORDER BY course_category, course_name "
             "LIMIT :limit OFFSET :offset"),
        {"limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


@router.post("/courses")
async def create_course(data: CourseCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("""INSERT INTO training_courses (course_code, course_name, course_category,
                 validity_months, is_mandatory, description)
                VALUES (:code, :name, :cat, :validity, :mandatory, :desc)
                ON CONFLICT (course_code) DO NOTHING"""),
        {"code": data.course_code, "name": data.course_name, "cat": data.course_category,
         "validity": data.validity_months, "mandatory": data.is_mandatory,
         "desc": data.description}
    )
    await db.commit()
    return {"status": "created"}


# ---- Role Requirements (which courses each role needs) ----

@router.get("/role-requirements/{role_id}")
async def get_role_requirements(role_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""SELECT trr.*, tc.course_code, tc.course_name, tc.course_category, tc.validity_months
                FROM training_role_requirements trr
                JOIN training_courses tc ON trr.course_id = tc.course_id
                WHERE trr.role_id = :rid"""),
        {"rid": role_id}
    )
    return [dict(r._mapping) for r in result]


@router.post("/role-requirements")
async def add_role_requirement(data: RoleRequirementCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO training_role_requirements (role_id, course_id) VALUES (:rid, :cid) "
             "ON CONFLICT (role_id, course_id) DO NOTHING"),
        {"rid": data.role_id, "cid": data.course_id}
    )
    await db.commit()
    return {"status": "added"}


# ---- Personnel ----

@router.post("/personnel/{project_id}")
async def register_personnel(project_id: str, data: PersonnelCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("""INSERT INTO personnel (personnel_id, project_id, badge_number, full_name,
                 role_id, discipline, contractor_company, mobilization_date)
                VALUES (gen_random_uuid(), :pid, :badge, :name, :rid, :disc, :company, :mob_date)"""),
        {"pid": project_id, "badge": data.badge_number, "name": data.full_name,
         "rid": data.role_id, "disc": data.discipline, "company": data.contractor_company,
         "mob_date": data.mobilization_date}
    )
    await db.commit()
    return {"status": "registered"}


@router.get("/personnel/{project_id}")
async def list_personnel(
    project_id: str,
    role_id: Optional[int] = None,
    discipline: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT p.*, tr.role_name, tr.role_category
               FROM personnel p
               LEFT JOIN training_roles tr ON p.role_id = tr.role_id
               WHERE p.project_id = :pid AND p.status = 'ACTIVE'"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if role_id:
        query += " AND p.role_id = :rid"
        params["rid"] = role_id
    if discipline:
        query += " AND p.discipline = :disc"
        params["disc"] = discipline
    query += " ORDER BY p.full_name LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


# ---- Training Records ----

@router.post("/records/{project_id}")
async def add_training_record(project_id: str, data: TrainingRecordCreate,
                              db: AsyncSession = Depends(get_db),
                              user: TokenData = Depends(get_current_user)):
    # The personnel row must belong to the path project.
    parent = await db.execute(
        text("SELECT personnel_id FROM personnel WHERE personnel_id = :pid_param AND project_id = :proj_id"),
        {"pid_param": data.personnel_id, "proj_id": project_id},
    )
    if parent.fetchone() is None:
        raise not_found("Personnel", data.personnel_id)
    await db.execute(
        text("""INSERT INTO personnel_training (record_id, personnel_id, project_id, course_id,
                 completion_date, expiry_date, certificate_ref, score, verified_by)
                VALUES (gen_random_uuid(), :pid, :proj_id, :cid, :cdate, :edate, :cert, :score, :vby)"""),
        {"pid": data.personnel_id, "proj_id": project_id, "cid": data.course_id,
         "cdate": data.completion_date, "edate": data.expiry_date,
         "cert": data.certificate_ref, "score": data.score,
         # verified_by is identity — derived from the token.
         "vby": user.username}
    )
    await db.commit()
    return {"status": "recorded"}


@router.get("/records/{project_id}")
async def list_training_records(project_id: str, personnel_id: Optional[str] = None,
                                page: int = 1, page_size: int = 500,
                                db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT pt.*, p.full_name, p.badge_number, tc.course_code, tc.course_name
               FROM personnel_training pt
               JOIN personnel p ON pt.personnel_id = p.personnel_id
                                AND p.project_id = pt.project_id
               JOIN training_courses tc ON pt.course_id = tc.course_id
               WHERE pt.project_id = :pid"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if personnel_id:
        query += " AND pt.personnel_id = :pid2"
        params["pid2"] = personnel_id
    query += " ORDER BY p.full_name, tc.course_name LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


# ---- Training Matrix & Compliance ----

@router.get("/matrix/{project_id}")
async def training_matrix(project_id: str, db: AsyncSession = Depends(get_db)):
    """Role-based training compliance matrix."""
    result = await db.execute(
        text("""SELECT tr.role_name, tc.course_name,
                       COUNT(DISTINCT p.personnel_id) AS total_personnel,
                       COUNT(DISTINCT pt.record_id) FILTER (
                           WHERE pt.expiry_date >= CURRENT_DATE OR pt.expiry_date IS NULL
                       ) AS certified_count,
                       ROUND(100.0 * COUNT(DISTINCT pt.record_id) FILTER (
                           WHERE pt.expiry_date >= CURRENT_DATE OR pt.expiry_date IS NULL
                       ) / NULLIF(COUNT(DISTINCT p.personnel_id), 0), 1) AS compliance_pct
                FROM training_role_requirements trr
                JOIN training_roles tr ON trr.role_id = tr.role_id
                JOIN training_courses tc ON trr.course_id = tc.course_id
                LEFT JOIN personnel p ON p.role_id = tr.role_id AND p.project_id = :pid AND p.status = 'ACTIVE'
                LEFT JOIN personnel_training pt ON pt.personnel_id = p.personnel_id AND pt.course_id = tc.course_id
                GROUP BY tr.role_name, tc.course_name
                HAVING COUNT(DISTINCT p.personnel_id) > 0
                ORDER BY tr.role_name, tc.course_name LIMIT 2000"""),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]


@router.get("/expiring-certifications/{project_id}")
async def expiring_certifications(project_id: str, days_ahead: int = 30,
                                  page: int = 1, page_size: int = 500,
                                  db: AsyncSession = Depends(get_db)):
    """List personnel with certifications expiring within N days."""
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("""SELECT p.full_name, p.badge_number, p.discipline, p.contractor_company,
                       tc.course_name, pt.certificate_ref, pt.expiry_date,
                       (pt.expiry_date - CURRENT_DATE) AS days_remaining
                FROM personnel_training pt
                JOIN personnel p ON pt.personnel_id = p.personnel_id
                                AND p.project_id = pt.project_id
                JOIN training_courses tc ON pt.course_id = tc.course_id
                WHERE pt.project_id = :pid
                  AND pt.expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + :days
                  AND p.status = 'ACTIVE'
                ORDER BY pt.expiry_date LIMIT :limit OFFSET :offset"""),
        {"pid": project_id, "days": days_ahead,
         "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


@router.get("/personnel-compliance/{project_id}/{personnel_id}")
async def personnel_compliance(project_id: str, personnel_id: str, db: AsyncSession = Depends(get_db)):
    """Single person training compliance vs role requirements."""
    result = await db.execute(
        text("""SELECT tc.course_code, tc.course_name, tc.course_category,
                       tc.is_mandatory, tc.validity_months,
                       pt.completion_date, pt.expiry_date, pt.certificate_ref,
                       CASE
                           WHEN pt.record_id IS NULL THEN 'MISSING'
                           WHEN pt.expiry_date < CURRENT_DATE THEN 'EXPIRED'
                           WHEN pt.expiry_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'EXPIRING'
                           ELSE 'VALID'
                       END AS status
                FROM training_role_requirements trr
                JOIN training_courses tc ON trr.course_id = tc.course_id
                JOIN personnel p ON p.role_id = trr.role_id AND p.personnel_id = :pid_param
                LEFT JOIN personnel_training pt ON pt.personnel_id = p.personnel_id
                    AND pt.course_id = tc.course_id
                    AND pt.project_id = :proj_id
                WHERE p.project_id = :proj_id
                ORDER BY tc.course_category, tc.course_name"""),
        {"pid_param": personnel_id, "proj_id": project_id}
    )
    return [dict(r._mapping) for r in result]
