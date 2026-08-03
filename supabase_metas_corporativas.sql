-- ════════════════════════════════════════════════════════════════
-- Metas Corporativas — schema Supabase
--
-- As 3 tabelas abaixo NÃO EXISTEM AINDA no projeto Supabase
-- (trdrqsrdtdezbopwahlo) — confirmado via REST em 2026-07-31
-- (PGRST205 "Could not find the table" para as 3).
--
-- Espelham a estrutura de campanhas / metas / regras_expandidas
-- (ver mcToRow/rowToMC e publicarMetasCorporativas() em
-- gestor-campanhas-dev.html), com uma diferença de propósito:
-- FK com ON DELETE CASCADE entre metas_corporativas_valores e
-- metas_corporativas — campanhas/metas NÃO tem isso (excluirCampanha
-- não limpa metas relacionadas, deixando linhas órfãs); aqui optei
-- por corrigir isso no novo schema em vez de repetir o gap.
--
-- ⚠ Rode isso no SQL Editor do Supabase. As políticas de RLS abaixo
-- são uma INFERÊNCIA a partir do comportamento observado via REST
-- com a anon key: SELECT em metas e regras_expandidas devolveu dados
-- normalmente (sem sessão autenticada — role "anon" no JWT), e um
-- INSERT anônimo em campanhas retornou 42501 "new row violates row-
-- level security policy". Isso sugere: SELECT liberado a anon
-- (Power BI Dataflow lê assim), INSERT/UPDATE/DELETE restrito a
-- admin autenticado. Não tive acesso para ler as policies reais
-- (precisaria da service_role key ou do dashboard) — se o padrão
-- real for diferente, ajuste antes de rodar.
-- ════════════════════════════════════════════════════════════════

-- ── 1. metas_corporativas ──────────────────────────────────────
create table if not exists public.metas_corporativas (
  cod         text primary key,
  nome        text not null,
  descricao   text default '',
  objetivo    text default '',
  ano         integer not null,
  agrupamento text not null check (agrupamento in ('canal','segmento','grupo','produto','empresa','vendedor')),
  flt         jsonb not null default '{"mode":"basico","sel":[],"adv":{}}'::jsonb,
  ordem       integer not null default 0,
  criado_em   timestamptz not null default now(),
  alterado_em timestamptz,
  criado_por  uuid references auth.users(id)
);

alter table public.metas_corporativas enable row level security;

create policy "metas_corporativas_select_anon"
  on public.metas_corporativas for select
  to anon, authenticated
  using (true);

create policy "metas_corporativas_write_admin"
  on public.metas_corporativas for all
  to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

-- ── 2. metas_corporativas_valores ──────────────────────────────
create table if not exists public.metas_corporativas_valores (
  id             bigint generated always as identity primary key,
  meta_cod       text not null references public.metas_corporativas(cod) on delete cascade,
  item_cod       text not null,
  item_nome      text not null default '',
  ano            integer not null,
  mes            integer not null check (mes between 1 and 12),
  valor          numeric not null default 0,
  atualizado_em  timestamptz not null default now(),
  atualizado_por uuid references auth.users(id),
  unique (meta_cod, item_cod, mes)
);

alter table public.metas_corporativas_valores enable row level security;

create policy "metas_corporativas_valores_select_anon"
  on public.metas_corporativas_valores for select
  to anon, authenticated
  using (true);

create policy "metas_corporativas_valores_write_admin"
  on public.metas_corporativas_valores for all
  to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

-- ── 3. metas_corporativas_expandidas (lida pelo Dataflow do Power BI) ──
create table if not exists public.metas_corporativas_expandidas (
  id              bigint generated always as identity primary key,
  cod_meta        text not null,
  meta            text not null default '',
  descricao       text default '',
  objetivo        text default '',
  agrupamento     text not null,
  ano             integer not null,
  dt_cadastro     text,
  dt_ultima_modif text,
  dt_ref          date not null,
  item_cod        text not null,
  item_nome       text not null default ''
);

alter table public.metas_corporativas_expandidas enable row level security;

-- Power BI Dataflow lê via PostgREST com a anon key (mesmo padrão de
-- regras_expandidas) — select liberado para anon, não só authenticated.
create policy "metas_corporativas_expandidas_select_anon"
  on public.metas_corporativas_expandidas for select
  to anon, authenticated
  using (true);

create policy "metas_corporativas_expandidas_write_admin"
  on public.metas_corporativas_expandidas for all
  to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

create index if not exists idx_mc_expandidas_cod_meta on public.metas_corporativas_expandidas(cod_meta);
create index if not exists idx_mc_valores_meta_cod on public.metas_corporativas_valores(meta_cod);
