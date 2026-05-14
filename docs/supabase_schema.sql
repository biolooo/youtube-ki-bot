create extension if not exists vector;

create table if not exists videos (
    video_id text primary key,
    title text not null,
    url text not null,
    published_at timestamptz,
    duration_seconds integer not null default 0,
    views bigint not null default 0,
    likes bigint not null default 0,
    comments bigint not null default 0,
    is_short boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists transcripts (
    video_id text primary key references videos(video_id) on delete cascade,
    transcript_source text,
    transcript_status text,
    language_code text,
    language text,
    is_generated boolean not null default false,
    transcript_text text not null default '',
    segments_json jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists video_analysis (
    video_id text primary key references videos(video_id) on delete cascade,
    hook_text text,
    platform_labels text[] not null default '{}',
    mentioned_platform_labels text[] not null default '{}',
    secondary_platform_labels text[] not null default '{}',
    format_labels text[] not null default '{}',
    hook_labels text[] not null default '{}',
    taxonomy_confidence_score double precision not null default 0,
    word_count integer not null default 0,
    question_count integer not null default 0,
    exclamation_count integer not null default 0,
    cta_present boolean not null default false,
    direct_address_present boolean not null default false,
    is_top_reference boolean not null default false,
    top_reference_group_count integer not null default 0,
    top_reference_groups text[] not null default '{}',
    like_rate double precision not null default 0,
    comment_rate double precision not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists reference_memberships (
    id bigint generated always as identity primary key,
    video_id text not null references videos(video_id) on delete cascade,
    group_type text not null,
    group_label text not null,
    selected_rank integer not null,
    group_video_count integer not null,
    selection_percent double precision not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_reference_memberships_video_id
    on reference_memberships(video_id);

create table if not exists reference_embeddings (
    video_id text primary key references videos(video_id) on delete cascade,
    model text not null,
    embedding vector(1536),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists reference_databases (
    id text primary key,
    name text not null,
    description text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists database_references (
    database_id text not null references reference_databases(id) on delete cascade,
    video_id text not null references videos(video_id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (database_id, video_id)
);

create index if not exists idx_database_references_video_id
    on database_references(video_id);

create table if not exists generation_requests (
    id uuid primary key default gen_random_uuid(),
    topic text not null,
    database_id text,
    platform text,
    format_label text,
    hook_label text,
    goal text,
    tone text,
    target_length_seconds integer,
    constraints text,
    freeform_brief text,
    retrieval_query text,
    top_k integer not null default 5,
    request_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists generated_scripts (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null references generation_requests(id) on delete cascade,
    variant_index integer not null default 1,
    title_ideas jsonb not null default '[]'::jsonb,
    hook text,
    script text,
    cta text,
    why_this_should_work jsonb not null default '[]'::jsonb,
    model text,
    response_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists script_reference_links (
    id bigint generated always as identity primary key,
    generated_script_id uuid not null references generated_scripts(id) on delete cascade,
    video_id text not null references videos(video_id) on delete cascade,
    retrieval_score double precision not null default 0,
    metadata_score double precision not null default 0,
    keyword_score double precision not null default 0,
    semantic_score double precision not null default 0,
    performance_score double precision not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_script_reference_links_script
    on script_reference_links(generated_script_id);

create table if not exists script_feedback (
    id bigint generated always as identity primary key,
    generated_script_id uuid not null references generated_scripts(id) on delete cascade,
    rating integer,
    liked boolean,
    notes text,
    created_at timestamptz not null default now()
);
