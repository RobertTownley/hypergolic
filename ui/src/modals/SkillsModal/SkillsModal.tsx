import { FlaskConicalIcon } from "lucide-react";
import type { SkillInfo } from "@/types/api";
import { Modal } from "@/shared/components/Modal";
import { Badge } from "@/shared/components/Badge";
import { EmptyState } from "@/shared/components/EmptyState";
import { sourceLabel } from "./useSkillsModal";
import styles from "./SkillsModal.module.css";

interface SkillsModalProps {
  skills: SkillInfo[];
  /** Ids the session has activated so far. */
  activated?: string[];
  onClose: () => void;
}

export function SkillsModal({ skills, activated = [], onClose }: SkillsModalProps) {
  const active = new Set(activated);
  return (
    <Modal
      onClose={onClose}
      title={`Skills (${skills.length})`}
      icon={<FlaskConicalIcon className={styles.headerIcon} />}
      width={600}
      maxHeight="80vh"
    >
      <div className={styles.skillsBody}>
        <div className={styles.groupSkills}>
          {skills.map((skill) => (
            <div key={skill.id} className={styles.skillItem}>
              <div className={styles.skillInfo}>
                <div className={styles.skillHeader}>
                  <span className={styles.skillName}>
                    {skill.name} <span className={styles.skillId}>(id: {skill.id})</span>
                  </span>
                  <div className={styles.chips}>
                    {active.has(skill.id) && <Badge variant="success" uppercase>activated</Badge>}
                    <Badge variant="muted" uppercase>{sourceLabel(skill.source)}</Badge>
                  </div>
                </div>
                <span className={styles.skillDescription}>{skill.description}</span>
              </div>
            </div>
          ))}
        </div>
        {skills.length === 0 && (
          <EmptyState text="No skills configured. Add skills in ~/.agents/config.json." />
        )}
      </div>
    </Modal>
  );
}
