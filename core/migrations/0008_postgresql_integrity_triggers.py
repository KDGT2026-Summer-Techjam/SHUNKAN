from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION core_validate_room_children()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM core_task
        WHERE room_id = NEW.id
          AND due_date IS NOT NULL
          AND (
              due_date < (NEW.starts_at AT TIME ZONE 'Asia/Tokyo')::date
              OR due_date > (NEW.ends_at AT TIME ZONE 'Asia/Tokyo')::date
          )
    ) THEN
        RAISE EXCEPTION 'Taskの期限はRoom期間内である必要があります。'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM core_momentlog
        WHERE room_id = NEW.id
          AND (
              (entry_type = 'moment'
               AND (occurred_at < NEW.starts_at OR occurred_at >= NEW.ends_at))
              OR
              (entry_type = 'reflection'
               AND (NEW.reflection_deadline_at IS NULL
                    OR occurred_at < NEW.ends_at
                    OR occurred_at > NEW.reflection_deadline_at))
          )
    ) THEN
        RAISE EXCEPTION 'MomentLogの発生日時はRoomの状態と期間に一致する必要があります。'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_room_children_integrity
BEFORE UPDATE OF starts_at, ends_at, reflection_deadline_at ON core_room
FOR EACH ROW
EXECUTE FUNCTION core_validate_room_children();

CREATE OR REPLACE FUNCTION core_validate_task_integrity()
RETURNS trigger AS $$
DECLARE
    category_room_id bigint;
    room_starts timestamptz;
    room_ends timestamptz;
BEGIN
    SELECT starts_at, ends_at
    INTO room_starts, room_ends
    FROM core_room
    WHERE id = NEW.room_id;

    IF NEW.category_id IS NOT NULL THEN
        SELECT room_id INTO category_room_id
        FROM core_category
        WHERE id = NEW.category_id;

        IF category_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'TaskとCategoryは同じRoomに属する必要があります。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.due_date IS NOT NULL AND (
        NEW.due_date < (room_starts AT TIME ZONE 'Asia/Tokyo')::date
        OR NEW.due_date > (room_ends AT TIME ZONE 'Asia/Tokyo')::date
    ) THEN
        RAISE EXCEPTION 'Taskの期限はRoom期間内である必要があります。'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_task_integrity
BEFORE INSERT OR UPDATE OF room_id, category_id, due_date ON core_task
FOR EACH ROW
EXECUTE FUNCTION core_validate_task_integrity();

CREATE OR REPLACE FUNCTION core_validate_category_integrity()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.room_id IS DISTINCT FROM OLD.room_id THEN
        IF EXISTS (
            SELECT 1 FROM core_task
            WHERE category_id = NEW.id AND room_id IS DISTINCT FROM NEW.room_id
        ) OR EXISTS (
            SELECT 1 FROM core_momentlog
            WHERE category_id = NEW.id AND room_id IS DISTINCT FROM NEW.room_id
        ) THEN
            RAISE EXCEPTION '関連データがあるCategoryのRoomは変更できません。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_category_integrity
BEFORE UPDATE OF room_id ON core_category
FOR EACH ROW
EXECUTE FUNCTION core_validate_category_integrity();

CREATE OR REPLACE FUNCTION core_validate_moment_log_integrity()
RETURNS trigger AS $$
DECLARE
    task_room_id bigint;
    category_room_id bigint;
    room_starts timestamptz;
    room_ends timestamptz;
    reflection_deadline timestamptz;
BEGIN
    SELECT starts_at, ends_at, reflection_deadline_at
    INTO room_starts, room_ends, reflection_deadline
    FROM core_room
    WHERE id = NEW.room_id;

    IF NEW.task_id IS NOT NULL THEN
        SELECT room_id INTO task_room_id
        FROM core_task
        WHERE id = NEW.task_id;

        IF task_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'MomentLogとTaskは同じRoomに属する必要があります。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.category_id IS NOT NULL THEN
        SELECT room_id INTO category_room_id
        FROM core_category
        WHERE id = NEW.category_id;

        IF category_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'MomentLogとCategoryは同じRoomに属する必要があります。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.entry_type = 'moment' THEN
        IF NEW.occurred_at < room_starts OR NEW.occurred_at >= room_ends THEN
            RAISE EXCEPTION '通常のSHUNKAN-logはRoom期間内である必要があります。'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.entry_type = 'reflection' THEN
        IF reflection_deadline IS NULL
           OR NEW.occurred_at < room_ends
           OR NEW.occurred_at > reflection_deadline THEN
            RAISE EXCEPTION '振り返りはRoom終了後から振り返り期限までである必要があります。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_moment_log_integrity
BEFORE INSERT OR UPDATE OF room_id, task_id, category_id, occurred_at, entry_type
ON core_momentlog
FOR EACH ROW
EXECUTE FUNCTION core_validate_moment_log_integrity();

CREATE OR REPLACE FUNCTION core_validate_photo_limit()
RETURNS trigger AS $$
DECLARE
    photo_count integer;
BEGIN
    PERFORM 1
    FROM core_momentlog
    WHERE id = NEW.moment_log_id
    FOR UPDATE;

    SELECT COUNT(*) INTO photo_count
    FROM core_photo
    WHERE moment_log_id = NEW.moment_log_id
      AND id IS DISTINCT FROM NEW.id;

    IF photo_count >= 3 THEN
        RAISE EXCEPTION '1件のSHUNKAN-logに保存できる写真は3枚までです。'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_photo_limit
BEFORE INSERT OR UPDATE OF moment_log_id ON core_photo
FOR EACH ROW
EXECUTE FUNCTION core_validate_photo_limit();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS core_photo_limit ON core_photo;
DROP TRIGGER IF EXISTS core_moment_log_integrity ON core_momentlog;
DROP TRIGGER IF EXISTS core_category_integrity ON core_category;
DROP TRIGGER IF EXISTS core_task_integrity ON core_task;
DROP TRIGGER IF EXISTS core_room_children_integrity ON core_room;

DROP FUNCTION IF EXISTS core_validate_photo_limit();
DROP FUNCTION IF EXISTS core_validate_moment_log_integrity();
DROP FUNCTION IF EXISTS core_validate_category_integrity();
DROP FUNCTION IF EXISTS core_validate_task_integrity();
DROP FUNCTION IF EXISTS core_validate_room_children();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_momentlog_moment_log_entry_type_is_valid"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
