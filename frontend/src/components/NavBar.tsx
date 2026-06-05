import { NavLink } from "react-router-dom";
import { Activity, GitMerge, Hash, MapPin, Network, Users } from "lucide-react";

const LINKS = [
  { to: "/", label: "Explorer", icon: Network, end: true },
  { to: "/jobs", label: "Jobs", icon: Activity, end: false },
  { to: "/accounts", label: "Accounts", icon: Users, end: false },
  { to: "/hashtags", label: "Hashtags", icon: Hash, end: false },
  { to: "/intersection", label: "Intersection", icon: GitMerge, end: false },
  { to: "/geo", label: "Geo Map", icon: MapPin, end: false },
];

export function NavBar() {
  return (
    <header className="nav">
      <a className="nav__brand" href="/" aria-label="xint home">
        <span className="nav__mark" aria-hidden>
          ✕
        </span>
        <span className="nav__wordmark">xint</span>
        <span className="nav__tag eyebrow eyebrow--sm">OSINT&nbsp;GRAPH</span>
      </a>

      <nav className="nav__links" aria-label="Primary">
        {LINKS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `nav__link${isActive ? " nav__link--active" : ""}`
            }
          >
            <Icon size={15} strokeWidth={1.75} aria-hidden />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <a
        className="nav__repo eyebrow eyebrow--sm"
        href="https://github.com/gahlautabhinav/xint"
        target="_blank"
        rel="noreferrer"
      >
        GITHUB&nbsp;↗
      </a>
    </header>
  );
}
