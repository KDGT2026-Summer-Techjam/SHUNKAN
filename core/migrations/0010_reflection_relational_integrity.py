from django.db import migrations


PREFLIGHT_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM core_momentlog
        WHERE entry_type = 'reflection'
          AND (task_id IS NOT NULL OR category_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION '既存の振り返りログにTaskまたはCategoryが関連付けられています。データを修正してから再実行してください。';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM core_photo photo
        JOIN core_momentlog moment_log ON moment_log.id = photo.moment_log_id
        WHERE moment_log.entry_type = 'reflection'
    ) THEN
        RAISE EXCEPTION '既存の振り返りログに写真が関連付けられています。データを修正してから再実行してください。';
    END IF;
END;
$$;
"""


FORWARD_SQL = PREFLIGHT_SQL + """
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

    IF NEW.entry_type = 'reflection'
       AND (NEW.task_id IS NOT NULL OR NEW.category_id IS NOT NULL) THEN
        RAISE EXCEPTION '振り返りログにはTask・Categoryを関連付けできません。'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.entry_type = 'reflection' AND EXISTS (
        SELECT 1 FROM core_photo WHERE moment_log_id = NEW.id
    ) THEN
        RAISE EXCEPTION '写真があるSHUNKAN-logを振り返りログには変更できません。'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.task_id IS NOT NULL THEN
        SELECT room_id INTO task_room_id FROM core_task WHERE id = NEW.task_id;
        IF task_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'MomentLogとTaskは同じRoomに属する必要があります。'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.category_id IS NOT NULL THEN
        SELECT room_id INTO category_room_id FROM core_category WHERE id = NEW.category_id;
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

CREATE OR REPLACE FUNCTION core_validate_photo_limit()
RETURNS trigger AS $$
DECLARE
    photo_count integer;
    parent_entry_type varchar(20);
BEGIN
    SELECT entry_type INTO parent_entry_type
    FROM core_momentlog
    WHERE id = NEW.moment_log_id
    FOR UPDATE;

    IF parent_entry_type = 'reflection' THEN
        RAISE EXCEPTION '振り返りログには写真を追加できません。'
            USING ERRCODE = '23514';
    END IF;

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
"""


REVERSE_SQL = """
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
    FROM core_room WHERE id = NEW.room_id;

    IF NEW.task_id IS NOT NULL THEN
        SELECT room_id INTO task_room_id FROM core_task WHERE id = NEW.task_id;
        IF task_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'MomentLogとTaskは同じRoomに属する必要があります.' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.category_id IS NOT NULL THEN
        SELECT room_id INTO category_room_id FROM core_category WHERE id = NEW.category_id;
        IF category_room_id IS DISTINCT FROM NEW.room_id THEN
            RAISE EXCEPTION 'MomentLogとCategoryは同じRoomに属する必要があります.' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.entry_type = 'moment' THEN
        IF NEW.occurred_at < room_starts OR NEW.occurred_at >= room_ends THEN
            RAISE EXCEPTION '通常のSHUNKAN-logはRoom期間内である必要があります。' USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.entry_type = 'reflection' THEN
        IF reflection_deadline IS NULL OR NEW.occurred_at < room_ends OR NEW.occurred_at > reflection_deadline THEN
            RAISE EXCEPTION '振り返りはRoom終了後から振り返り期限までである必要があります。' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION core_validate_photo_limit()
RETURNS trigger AS $$
DECLARE
    photo_count integer;
BEGIN
    PERFORM 1 FROM core_momentlog WHERE id = NEW.moment_log_id FOR UPDATE;
    SELECT COUNT(*) INTO photo_count FROM core_photo
    WHERE moment_log_id = NEW.moment_log_id AND id IS DISTINCT FROM NEW.id;
    IF photo_count >= 3 THEN
        RAISE EXCEPTION '1件のSHUNKAN-logに保存できる写真は3枚までです。' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0009_photo_captured_at_photo_captured_at_source")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
