select distinct source.path,
       coalesce(json_extract(source.frontmatter, '$.title'), source.title, source.stem) as label
from documents as source, json_each(coalesce(json_extract(source.frontmatter, '$.links'), '[]')) as link
where link.value = :insitu_path
  and (:insitu_path like '.context/reference/%'
       or source.path not like '.context/reference/%')
order by source.path;
