import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildFeatures.dockerRegistryConnections
import jetbrains.buildServer.configs.kotlin.buildFeatures.perfmon
import jetbrains.buildServer.configs.kotlin.buildSteps.SSHUpload
import jetbrains.buildServer.configs.kotlin.buildSteps.sshExec
import jetbrains.buildServer.configs.kotlin.buildSteps.sshUpload
import jetbrains.buildServer.configs.kotlin.projectFeatures.dockerRegistry
import jetbrains.buildServer.configs.kotlin.triggers.vcs
import jetbrains.buildServer.configs.kotlin.vcs.GitVcsRoot

/*
The settings script is an entry point for defining a TeamCity
project hierarchy. The script should contain a single call to the
project() function with a Project instance or an init function as
an argument.

VcsRoots, BuildTypes, Templates, and subprojects can be
registered inside the project using the vcsRoot(), buildType(),
template(), and subProject() methods respectively.

To debug settings scripts in command-line, run the

    mvnDebug org.jetbrains.teamcity:teamcity-configs-maven-plugin:generate

command and attach your debugger to the port 8000.

To debug in IntelliJ Idea, open the 'Maven Projects' tool window (View
-> Tool Windows -> Maven Projects), find the generate task node
(Plugins -> teamcity-configs -> teamcity-configs:generate), the
'Debug' option is available in the context menu for the task.
*/

version = "2025.07"

project {

    vcsRoot(GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1)

    buildType(BuildWeb)
    buildType(BuildApi)

    params {
        param("server-address", "travelplanner.solutions")
        param("server-project-route", "/home/vpcuser/TravelPlaner")
        password("env.web", "credentialsJSON:a0f500c5-b36e-49ca-957f-14ab39bd9e69")
        param("server-username", "vpcuser")
        password("env.api", "credentialsJSON:8920a480-dbd6-41e3-bc10-f54fb7c56fa2")
    }

    features {
        dockerRegistry {
            id = "PROJECT_EXT_2"
            name = "Docker Registry"
            userName = "0sethmccarthy0"
            password = "credentialsJSON:2f031eb5-503b-46bf-a795-ed837567ac74"
        }
    }
}

object BuildApi : BuildType({
    name = "Build-API"

    vcs {
        root(DslContext.settingsRoot)
    }

    steps {
        sshExec {
            name = "Clear Legacy Deployment"
            id = "Clear_Legacy_Deployment"
            commands = """
                cd %server-project-route%
                rm -rf backend
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/backend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshUpload {
            name = "Transfer to the Remote Server"
            id = "Transfer_to_the_Remote_Server"
            transportProtocol = SSHUpload.TransportProtocol.SCP
            sourcePath = "backend/"
            targetUrl = "%server-address%:%server-project-route%/backend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Create .env.prod"
            id = "Create_env_prod"
            commands = """
                cd %server-project-route%/backend
                cat <<'EOF' > .env.prod
                %env.api%
                EOF
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/backend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Docker Compose"
            id = "Docker_Compose"
            commands = """
                cd %server-project-route%/backend
                sudo docker compose --env-file .env.prod -f docker-compose-prod.yml up --build -d
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/backend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
    }

    triggers {
        vcs {
        }
    }

    features {
        perfmon {
        }
        dockerRegistryConnections {
            loginToRegistry = on {
                dockerRegistryId = "PROJECT_EXT_2"
            }
        }
    }
})

object BuildWeb : BuildType({
    name = "Build-Web"

    vcs {
        root(GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1)
    }

    steps {
        sshExec {
            name = "Clear Legacy Deployment"
            id = "Clear_Legacy_Deployment"
            commands = """
                cd %server-project-route%
                rm -rf frontend
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/frontend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshUpload {
            name = "Transfer to the Remote Server"
            id = "Transfer_to_the_Remote_Server"
            transportProtocol = SSHUpload.TransportProtocol.SCP
            sourcePath = "frontend/"
            targetUrl = "%server-address%:%server-project-route%/frontend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Create .env.prod"
            id = "Create_env_prod"
            commands = """
                cd %server-project-route%/backend
                cat <<'EOF' > .env.prod
                %env.web%
                EOF
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/frontend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Docker Compose"
            id = "Docker_Compose"
            commands = """
                cd %server-project-route%//frontend
                sudo docker compose --env-file .env.prod -f docker-compose-prod.yml up --build -d
            """.trimIndent()
            targetUrl = "%server-address%:%server-project-route%/frontend"
            authMethod = uploadedKey {
                username = "%server-username%"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
    }

    triggers {
        vcs {
        }
    }

    features {
        perfmon {
        }
    }
})

object GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1 : GitVcsRoot({
    name = "git@github.com:0SRAF0/TravelPlanner.git#refs/heads/main (1)"
    url = "git@github.com:0SRAF0/TravelPlanner.git"
    branch = "refs/heads/main"
    branchSpec = "refs/heads/*"
    authMethod = uploadedKey {
        uploadedKey = "seth"
        passphrase = "credentialsJSON:e325be5f-9914-49c1-b84c-4aa2b81d8987"
    }
})
