# app/services/field_state_transition.py — валидатор переходов состояний Field
# Это чистая бизнес-логика, не привязана к контроллерам

from typing import Optional, Set, Tuple
from app.models import FieldStatusEnum


class FieldStateTransitionValidator:
    """
    Валидатор переходов между состояниями Field.
    Реализует бизнес-правила:
    - Запрещённые переходы
    - Последовательность обработки при болезни
    - Правила перехода из каждого состояния
    """

    # ── Запрещённые переходы (ничего не может перейти в них из определённых состояний) ──
    FORBIDDEN_TRANSITIONS = {
        FieldStatusEnum.preparation: {FieldStatusEnum.disease},
        FieldStatusEnum.field_free: {FieldStatusEnum.disease},
    }

    # ── Допустимые переходы из каждого состояния ──
    ALLOWED_TRANSITIONS = {
        FieldStatusEnum.preparation: {
            FieldStatusEnum.sowing,
        },
        FieldStatusEnum.sowing: {
            FieldStatusEnum.monitoring,
            FieldStatusEnum.disease,  # Можно заболеть на этапе посева
        },
        FieldStatusEnum.monitoring: {
            FieldStatusEnum.harvesting,
            FieldStatusEnum.disease,  # Болезнь во время роста
        },
        FieldStatusEnum.harvesting: {
            FieldStatusEnum.post_harvest_processing,
        },
        FieldStatusEnum.post_harvest_processing: {
            FieldStatusEnum.field_free,
        },
        FieldStatusEnum.field_free: {
            FieldStatusEnum.preparation,  # Новый сезон
        },
        # ── Специальное правило для болезни ──
        # Из болезни можно перейти в одну из трёх процедур восстановления
        # Порядок: residue_removal → deep_plowing → chemical_treatment
        # Но можно пропустить любую один (кроме всех)
        FieldStatusEnum.disease: {
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
        },
        FieldStatusEnum.residue_removal: {
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,  # Или сразу в свободное
        },
        FieldStatusEnum.deep_plowing: {
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,
        },
        FieldStatusEnum.chemical_treatment: {
            FieldStatusEnum.field_free,
        },
    }

    @staticmethod
    def can_transition(
        current_status: FieldStatusEnum,
        new_status: FieldStatusEnum,
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить, разрешен ли переход.
        
        Returns:
            (is_allowed, error_message)
            is_allowed=True если переход допустим
            is_allowed=False с error_message если нет
        """
        # Проверка 1: нельзя переходить в то же состояние
        if current_status == new_status:
            return False, f"Поле уже в состоянии {new_status.value}"

        # Проверка 2: текущее состояние вообще имеет исходящие переходы?
        if current_status not in FieldStateTransitionValidator.ALLOWED_TRANSITIONS:
            return False, f"Из состояния {current_status.value} нельзя переходить в другие состояния"

        # Проверка 3: целевое состояние в списке допустимых?
        allowed = FieldStateTransitionValidator.ALLOWED_TRANSITIONS[current_status]
        if new_status not in allowed:
            return False, (
                f"Переход {current_status.value} → {new_status.value} не разрешён. "
                f"Допустимые переходы: {', '.join(s.value for s in allowed)}"
            )

        # Проверка 4: запрещённый переход?
        if current_status in FieldStateTransitionValidator.FORBIDDEN_TRANSITIONS:
            forbidden = FieldStateTransitionValidator.FORBIDDEN_TRANSITIONS[current_status]
            if new_status in forbidden:
                return False, (
                    f"Переход {current_status.value} → {new_status.value} запрещён системой"
                )

        # Проверка 5: специальное правило для последовательности после болезни
        # Если мы в disease и переходим в одну из процедур, проверяем
        if current_status == FieldStatusEnum.disease:
            # Все переходы уже в ALLOWED_TRANSITIONS, но можно добавить дополнительную логику
            pass

        # Проверка 6: если переходим ИЗ residue_removal/deep_plowing в field_free,
        # это допустимо (можно пропустить оставшиеся этапы)
        if current_status in {
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
        } and new_status == FieldStatusEnum.field_free:
            # Это разрешено — можно "скипнуть" оставшиеся этапы
            pass

        return True, None

    @staticmethod
    def get_available_transitions(current_status: FieldStatusEnum) -> Set[FieldStatusEnum]:
        """
        Получить набор допустимых целевых состояний из текущего.
        """
        if current_status not in FieldStateTransitionValidator.ALLOWED_TRANSITIONS:
            return set()
        return FieldStateTransitionValidator.ALLOWED_TRANSITIONS[current_status]

    @staticmethod
    def get_status_description(status: FieldStatusEnum) -> str:
        """Человеческое описание состояния."""
        descriptions = {
            FieldStatusEnum.preparation: "Подготовка земли (вспашка, выравнивание, внесение удобрений)",
            FieldStatusEnum.sowing: "Посев (в процессе посадки семян)",
            FieldStatusEnum.monitoring: "Мониторинг (рост пшеницы, сбор данных pH и влажности)",
            FieldStatusEnum.harvesting: "Сбор урожая (уборка комбайном)",
            FieldStatusEnum.post_harvest_processing: "Послеуборочная обработка (сушка, очистка)",
            FieldStatusEnum.field_free: "Поле свободно (готово к новому циклу или отдыху)",
            FieldStatusEnum.disease: "Болезнь/Карантин (обнаружена болезнь, поле на обработке)",
            FieldStatusEnum.residue_removal: "Уничтожение растительных остатков (шредирование соломы)",
            FieldStatusEnum.deep_plowing: "Глубокая зяблевая вспашка 20–25 см (подготовка почвы)",
            FieldStatusEnum.chemical_treatment: "Химическая обработка (гербициды/фунгициды от остатков болезни)",
        }
        return descriptions.get(status, status.value)

    @staticmethod
    def get_recovery_sequence() -> list:
        """
        Получить рекомендуемую последовательность восстановления после болезни.
        После disease: residue_removal → deep_plowing → chemical_treatment → field_free
        """
        return [
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,
        ]
