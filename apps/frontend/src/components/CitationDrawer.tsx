import { ExternalLink, FileSearch } from 'lucide-react';

import { Citation } from '../types';
import { safeExternalUrl, withoutDatasetYear } from '../lib/structured';

export function CitationDrawer({
  citations,
  currentDataset = false,
}: {
  citations: Citation[];
  currentDataset?: boolean;
}) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <details className="citation-drawer">
      <summary>
        <FileSearch size={16} aria-hidden="true" />
        Kiểm tra nguồn ({citations.length})
      </summary>
      <ol>
        {citations.map((citation) => {
          const safeUrl = safeExternalUrl(citation.url);
          const title = currentDataset
            ? withoutDatasetYear(citation.title) || 'Nguồn dữ liệu đã cung cấp'
            : citation.title;
          const excerpt = currentDataset && citation.excerpt
            ? withoutDatasetYear(citation.excerpt)
            : citation.excerpt;
          return (
            <li key={`${citation.source_id}:${citation.title}`}>
              <div className="citation-heading">
                {safeUrl ? (
                  <a href={safeUrl} rel="noopener noreferrer" target="_blank">
                    {title}
                    <ExternalLink size={14} aria-hidden="true" />
                  </a>
                ) : (
                  <strong>{title}</strong>
                )}
              </div>
              <dl className="source-metadata">
                {!currentDataset ? (
                  <div>
                    <dt>Mã nguồn</dt>
                    <dd>{citation.source_id}</dd>
                  </div>
                ) : null}
                {citation.publisher ? (
                  <div>
                    <dt>Đơn vị công bố</dt>
                    <dd>
                      {currentDataset
                        ? withoutDatasetYear(citation.publisher)
                        : citation.publisher}
                    </dd>
                  </div>
                ) : null}
                {citation.source_page ? (
                  <div>
                    <dt>Trang</dt>
                    <dd>{citation.source_page}</dd>
                  </div>
                ) : null}
                {!currentDataset && citation.effective_from ? (
                  <div>
                    <dt>Hiệu lực từ</dt>
                    <dd>{citation.effective_from}</dd>
                  </div>
                ) : null}
              </dl>
              {excerpt ? <p className="citation-excerpt">{excerpt}</p> : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
