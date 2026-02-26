"""
Generators for Enterprise Requirements Engineering System.

This package contains LLM-powered generators for:
- User Stories (from Requirements)
- API Specifications (OpenAPI 3.0)
- Data Dictionary (Domain Model)
- Test Cases (Gherkin/BDD)
- Tech Stack Recommendations
- Task Lists (from Work Packages)
- UX Design Artifacts
- UI Design Specifications
- Realtime/WebSocket Specifications (AsyncAPI 2.6)
- Architecture Design (C4 Diagrams)
- State Machines (Entity Lifecycle)
- Component Compositions (Screen-Component Mapping)
- Config & Environment (Docker, K8s, CI/CD)
- Test Data Factories (factory_boy + Seed SQL)
"""

from .user_story_generator import UserStoryGenerator, UserStory, Epic
from .api_spec_generator import APISpecGenerator, APIEndpoint
from .data_dictionary_generator import DataDictionaryGenerator, Entity, DataDictionary
from .test_case_generator import TestCaseGenerator, TestCase
from .tech_stack_generator import TechStackGenerator, TechStack, save_tech_stack
from .task_generator import TaskGenerator, Task, TaskBreakdown, save_task_list
from .ux_design_generator import UXDesignGenerator, UXDesignSpec, Persona, UserFlow, save_ux_design
from .ui_design_generator import UIDesignGenerator, UIDesignSpec, UIComponent, Screen, save_ui_design
from .presentation_generator import PresentationGenerator, PresentationAnalyzer, HTMLPage
from .link_config_generator import LinkConfigGenerator, LinkConfig, generate_link_config
from .realtime_spec_generator import RealtimeSpecGenerator, RealtimeSpec
from .architecture_generator import ArchitectureGenerator, ArchitectureSpec, save_architecture
from .state_machine_generator import StateMachineGenerator, StateMachine, save_state_machines
from .component_composition_generator import ComponentCompositionGenerator, ComponentMatrix, save_compositions
from .config_generator import ConfigGenerator, InfraConfig, save_config
from .test_factory_generator import TestFactoryGenerator, EntityFactory, save_test_factories

__all__ = [
    "UserStoryGenerator",
    "UserStory",
    "Epic",
    "APISpecGenerator",
    "APIEndpoint",
    "DataDictionaryGenerator",
    "Entity",
    "DataDictionary",
    "TestCaseGenerator",
    "TestCase",
    # New generators
    "TechStackGenerator",
    "TechStack",
    "save_tech_stack",
    "TaskGenerator",
    "Task",
    "TaskBreakdown",
    "save_task_list",
    "UXDesignGenerator",
    "UXDesignSpec",
    "Persona",
    "UserFlow",
    "save_ux_design",
    "UIDesignGenerator",
    "UIDesignSpec",
    "UIComponent",
    "Screen",
    "save_ui_design",
    # Presentation Generator
    "PresentationGenerator",
    "PresentationAnalyzer",
    "HTMLPage",
    # Link Config Generator
    "LinkConfigGenerator",
    "LinkConfig",
    "generate_link_config",
    # Realtime Spec Generator
    "RealtimeSpecGenerator",
    "RealtimeSpec",
    # Architecture Generator
    "ArchitectureGenerator",
    "ArchitectureSpec",
    "save_architecture",
    # State Machine Generator
    "StateMachineGenerator",
    "StateMachine",
    "save_state_machines",
    # Component Composition Generator
    "ComponentCompositionGenerator",
    "ComponentMatrix",
    "save_compositions",
    # Config & Environment Generator
    "ConfigGenerator",
    "InfraConfig",
    "save_config",
    # Test Data Factory Generator
    "TestFactoryGenerator",
    "EntityFactory",
    "save_test_factories",
]
