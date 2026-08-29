-- Tanca el forat de la 0006: athlete_answer va néixer amb els grants per
-- defecte de Supabase (anon amb select; RLS l'amagava, però la política de
-- la 0005 és que anon no té ni el permís). I evita que torni a passar:
-- les taules que es creïn a partir d'ara neixen SENSE grants per a anon
-- ni authenticated — cada migració concedeix explícitament el que toqui.

revoke all on athlete_answer from anon;

alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated;
