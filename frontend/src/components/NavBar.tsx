import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, GitMerge, Hash, MapPin, Network, ShieldAlert, Users } from "lucide-react";
import { api } from "@/lib/api";
import "../features/bias/bias.css";

const LINKS = [
  { to: "/", label: "Explorer", icon: Network, end: true },
  { to: "/jobs", label: "Jobs", icon: Activity, end: false },
  { to: "/accounts", label: "Accounts", icon: Users, end: false },
  { to: "/hashtags", label: "Hashtags", icon: Hash, end: false },
  { to: "/intersection", label: "Intersection", icon: GitMerge, end: false },
  { to: "/geo", label: "Geo Map", icon: MapPin, end: false },
];

function BiasStatusDot() {
  const { data } = useQuery({
    queryKey: ["bias-status"],
    queryFn: api.getBiasStatus,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const online = data?.connected === true;
  return (
    <span
      className={`nav__bias-dot ${online ? "nav__bias-dot--online" : "nav__bias-dot--offline"}`}
      title={online ? "Bias agent: online" : "Bias agent: offline"}
      aria-hidden
    />
  );
}

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
        <NavLink
          to="/bias"
          end={false}
          className={({ isActive }) =>
            `nav__link${isActive ? " nav__link--active" : ""}`
          }
        >
          <ShieldAlert size={15} strokeWidth={1.75} aria-hidden />
          <span>Bias</span>
          <BiasStatusDot />
        </NavLink>
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
