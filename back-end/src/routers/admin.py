from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_, or_, not_

from dependencies import get_session, require_roles
from models.relational_models import Admin
from schemas.admin import AdminCreate, AdminUpdate
from schemas.relational_schemas import RelationalAdminPublic
from utilities.authentication import get_password_hash, oauth2_scheme
from utilities.enumerables import LogicalOperator, AdminRole, AdminStatus

router = APIRouter()

@router.get(
    "/admins/",
    response_model=list[RelationalAdminPublic] | RelationalAdminPublic,
)
async def get_admins(
    *,
    session: AsyncSession = Depends(get_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=100),
    _user: dict = Depends(
        require_roles(
            AdminRole.SUPER_ADMIN.value,
            AdminRole.GENERAL_ADMIN.value,
        )
    ),
    _token: str = Depends(oauth2_scheme),
):
    if _user["role"] == AdminRole.GENERAL_ADMIN.value:
        admin = await session.get(Admin, _user["id"])

        return admin

    admins_query = select(Admin).offset(offset).limit(limit)
    admins = await session.execute(admins_query)

    admins_list = admins.scalars().all()

    return admins_list

@router.post(
    "/admins/",
    response_model=RelationalAdminPublic,
)
async def create_admin(
        *,
        session: AsyncSession = Depends(get_session),
        admin_create: AdminCreate,
        _user: dict = Depends(
            require_roles(
                AdminRole.SUPER_ADMIN.value,
                AdminRole.GENERAL_ADMIN.value,
            )
        ),
        _token: str = Depends(oauth2_scheme),
):
    if _user["role"] == AdminRole.GENERAL_ADMIN.value:
        final_role = AdminRole.GENERAL_ADMIN.value
    else:
        final_role = admin_create.role

    # Securely hash password before persistence
    hashed_password = get_password_hash(admin_create.password)

    try:

        db_admin = Admin(
            name_prefix=admin_create.name_prefix,
            first_name=admin_create.first_name,
            middle_name=admin_create.middle_name,
            last_name=admin_create.last_name,
            name_suffix=admin_create.name_suffix,
            national_id=admin_create.national_id,
            gender=admin_create.gender,
            birthday=admin_create.birthday,
            phone=admin_create.phone,
            address=admin_create.address,
            username=admin_create.username,
            email=admin_create.email,
            role=final_role,
            status=admin_create.status,
            password=hashed_password,
        )


        # Persist to database with explicit transaction control
        session.add(db_admin)
        await session.commit()
        await session.refresh(db_admin)

        return db_admin

    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="نام کاربری یا پست الکترونیکی یا کد ملی قبلا ثبت شده است"
        )
    except Exception as e:
        # Critical error handling with transaction rollback
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"{e}خطا در ایجاد ادمین: "
        )

@router.get(
    "/admins/{admin_id}",
    response_model=RelationalAdminPublic,
)
async def get_admin(
        *,
        session: AsyncSession = Depends(get_session),
        admin_id: UUID,
        _user: dict = Depends(
            require_roles(
                AdminRole.SUPER_ADMIN.value,
                AdminRole.GENERAL_ADMIN.value,
            )
        ),
        _token: str = Depends(oauth2_scheme),
):
    """
    Retrieves the detailed information of a specific author, including their associated posts.

    This endpoint allows authenticated users with appropriate roles (FULL, ADMIN, or AUTHOR) to retrieve
    an author's public information and their posts by providing the author's unique ID.

    - **author_id**: The unique identifier of the author.
    """
    if _user["role"] == AdminRole.GENERAL_ADMIN.value and admin_id != UUID(_user["id"]):
        raise HTTPException(status_code=403,
                            detail="شما دسترسی لازم برای مشاهده اطلاعات ادمین های  دیگر را ندارید")

    # Attempt to retrieve the author record from the database
    admin = await session.get(Admin, admin_id)

    # If the author is found, process the data and add necessary links
    if not admin:
        raise HTTPException(status_code=404, detail="ادمین پیدا نشد")

    return admin



@router.patch(
    "/admins/{admin_id}",
    response_model=RelationalAdminPublic,
)
async def patch_admin(
        *,
        session: AsyncSession = Depends(get_session),
        admin_id: UUID,
        admin_update: AdminUpdate,
        _user: dict = Depends(
            require_roles(
                AdminRole.SUPER_ADMIN.value,
                AdminRole.GENERAL_ADMIN.value,
            )
        ),
        _token: str = Depends(oauth2_scheme),
):

    if _user["role"] == AdminRole.GENERAL_ADMIN.value and admin_id != UUID(_user["id"]):
        raise HTTPException(status_code=403,
                            detail="شما دسترسی لازم برای ویرایش اطلاعات ادمین های  دیگر را ندارید")

    # Retrieve the author record from the database using the provided ID.
    admin = await session.get(Admin, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="ادمین پیدا نشد")

    # Prepare the update data, excluding unset fields.
    admin_data = admin_update.model_dump(exclude_unset=True)
    extra_data = {}

    # If the password is being updated, hash it before saving.
    if "password" in admin_data.keys():
        password = admin_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["password"] = hashed_password

    # Apply the update to the author record.
    admin.sqlmodel_update(admin_data, update=extra_data)

    # Commit the transaction and refresh the instance to reflect the changes.
    session.add(admin)
    await session.commit()
    await session.refresh(admin)

    return admin


@router.delete(
    "/admins/{admin_id}",
    response_model=RelationalAdminPublic,
)
async def delete_admin(
    *,
    session: AsyncSession = Depends(get_session),
    admin_id: UUID,
    _user: dict = Depends(
        require_roles(
            AdminRole.SUPER_ADMIN.value,
            AdminRole.GENERAL_ADMIN.value,
        )
    ),
    _token: str = Depends(oauth2_scheme),
):
    if _user["role"] == AdminRole.GENERAL_ADMIN.value and admin_id != UUID(_user["id"]):
        raise HTTPException(status_code=403,
                            detail="شما دسترسی لازم برای حذف ادمین های  دیگر را ندارید")

    # Fetch the author record from the database using the provided ID.
    admin = await session.get(Admin, admin_id)

    # If the author is not found, raise a 404 Not Found error.
    if not admin:
        raise HTTPException(status_code=404, detail="ادمین پیدا نشد")


    # Proceed to delete the author if the above conditions are met.
    await session.delete(admin)
    await session.commit()  # Commit the transaction to apply the changes

    # Return the author information after deletion.
    return admin

@router.get(
    "/admins/search/",
    response_model=list[RelationalAdminPublic],
)
async def search_admins(
        *,
        session: AsyncSession = Depends(get_session),
        username: str | None = None,
        email: EmailStr | None = None,
        role: AdminRole | None = None,
        status: AdminStatus | None = None,
        national_id: str | None = None,
        gender: str | None = None,
        phone: int | None = None,
        operator: LogicalOperator,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, le=100),
        _user: dict = Depends(
            require_roles(
                AdminRole.SUPER_ADMIN.value,
                AdminRole.GENERAL_ADMIN.value,
            )
        ),
        _token: str = Depends(oauth2_scheme),
):

    conditions = []  # Initialize the list of filter conditions

    # Start building the query to fetch authors with pagination.
    query = select(Admin).offset(offset).limit(limit)

    # Add filters to the conditions list if the corresponding arguments are provided.
    if username:
        conditions.append(Admin.username.ilike(f"%{username}%"))
    if email:
        conditions.append(Admin.email == email)
    if role:
        conditions.append(Admin.role == role)
    if status:
        conditions.append(Admin.status == status)
    if national_id:
        conditions.append(Admin.national_id == national_id)
    if gender:
        conditions.append(Admin.gender == gender)
    if phone:
        conditions.append(Admin.phone == phone)


    # If no conditions are provided, raise an error.
    if not conditions:
        raise HTTPException(status_code=400, detail="هیچ مقداری برای جست و جو وجود ندارد")

    # Apply the logical operator (AND, OR, or NOT) to combine the conditions.
    if operator == LogicalOperator.AND:
        query = query.where(and_(*conditions))
    elif operator == LogicalOperator.OR:
        query = query.where(or_(*conditions))
    elif operator == LogicalOperator.NOT:
        query = query.where(and_(not_(*conditions)))
    else:
        raise HTTPException(status_code=400, detail="عملگر نامعتبر مشخص شده است")

    # Execute the query asynchronously.
    admin_db = await session.execute(query)
    admins = admin_db.scalars().all()  # Retrieve all authors that match the conditions

    # If no authors are found, raise a "not found" error.
    if not admins:
        raise HTTPException(status_code=404, detail="مشتری پیدا نشد")

    return admins

