import { BRAND_CONFIG } from '../config/brandConfig';

interface SidebarBrandFooterProps {
  collapsed: boolean;
}

export function SidebarBrandFooter({ collapsed }: SidebarBrandFooterProps) {
  return (
    <div
      className={`sidebar-brand-footer ${collapsed ? 'sidebar-brand-footer-collapsed' : ''}`}
      data-layer="Brand / Sidebar Footer"
      title="Ready for daily review"
    >
      <span className="sr-only">Ready for daily review</span>
      <div
        className="sidebar-brand-footer-content"
        title={collapsed ? BRAND_CONFIG.companyName : undefined}
      >
        <div className="sidebar-brand-footer-logo-wrap">
          <img
            src={BRAND_CONFIG.logoUrl}
            alt={BRAND_CONFIG.companyName}
            className="sidebar-brand-footer-logo"
          />
        </div>
        {!collapsed && (
          <div className="sidebar-brand-footer-text">
            <span className="sidebar-brand-footer-name">{BRAND_CONFIG.companyName}</span>
            <span className="sidebar-brand-footer-copyright">{BRAND_CONFIG.copyrightText}</span>
          </div>
        )}
      </div>
    </div>
  );
}
